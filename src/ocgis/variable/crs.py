import abc
import itertools
import tempfile

import numpy as np
from fiona.crs import from_string, to_string
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseMultipartGeometry

from ocgis import constants
from ocgis.base import AbstractInterfaceObject
from ocgis.constants import MPIWriteMode, WrappedState, WrapAction, KeywordArguments
from ocgis.environment import osr
from ocgis.exc import ProjectionCoordinateNotFound, ProjectionDoesNotMatch
from ocgis.spatial.wrap import GeometryWrapper, CoordinateArrayWrapper
from ocgis.util.helpers import iter_array, get_iter
from ocgis.vm.mpi import get_standard_comm_state

SpatialReference = osr.SpatialReference


class CoordinateReferenceSystem(AbstractInterfaceObject):
    """
    Defines a coordinate system objects. One of ``value``, ``proj4``, or ``epsg`` is required.

    :param value: (``=None``) A dictionary representation of the coordinate system with PROJ.4 paramters as keys.
    :type value: dict
    :param proj4: (``=None``) A PROJ.4 string.
    :type proj4: str
    :param epsg: (``=None``) An EPSG code.
    :type epsg: int
    :param name: (``=:attr:`ocgis.constants.DEFAULT_COORDINATE_SYSTEM_NAME```) A custom name for the coordinate system.
    :type name: str
    """

    # tdk: implement reading proj4 attribute from coordinate systems if present
    def __init__(self, value=None, proj4=None, epsg=None, name=constants.DEFAULT_COORDINATE_SYSTEM_NAME):
        self.name = name
        # Allows operations on data variables to look through an empty dimension list. Alleviates instance checking.
        self.dimensions = tuple()
        self.dimension_names = tuple()
        self.ndim = 0
        self.has_bounds = False
        self.dist = None
        self.ranks = None
        self._is_empty = False

        # Add a special check for init keys in value dictionary.
        if value is not None:
            if 'init' in value and value.values()[0].startswith('epsg'):
                epsg = int(value.values()[0].split(':')[1])
                value = None

        if value is None:
            if proj4 is not None:
                value = from_string(proj4)
            elif epsg is not None:
                sr = SpatialReference()
                sr.ImportFromEPSG(epsg)
                value = from_string(sr.ExportToProj4())
            else:
                msg = 'A value dictionary, PROJ.4 string, or EPSG code is required.'
                raise ValueError(msg)
        else:
            # Remove unicode to avoid strange issues with proj and fiona.
            for k, v in value.iteritems():
                if type(v) == unicode:
                    value[k] = str(v)
                else:
                    try:
                        value[k] = v.tolist()
                    # this may be a numpy arr that needs conversion
                    except AttributeError:
                        continue

        sr = SpatialReference()
        sr.ImportFromProj4(to_string(value))
        self.value = from_string(sr.ExportToProj4())

        try:
            assert self.value != {}
        except AssertionError:
            msg = 'Empty CRS: The conversion to PROJ.4 may have failed. The CRS value is: {0}'.format(value)
            raise ValueError(msg)

    def __eq__(self, other):
        try:
            if self.sr.IsSame(other.sr) == 1:
                ret = True
            else:
                ret = False
        except AttributeError:
            # likely a nonetype of other object type
            if other is None or not isinstance(other, self.__class__):
                ret = False
            else:
                raise
        return ret

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return str(self.value)

    @property
    def has_allocated_value(self):
        return False

    @property
    def has_distributed_dimension(self):
        return False

    @property
    def has_initialized_parent(self):
        return False

    @property
    def is_empty(self):
        return self._is_empty

    @property
    def is_geographic(self):
        return bool(self.sr.IsGeographic())

    @property
    def is_orphaned(self):
        return True

    @property
    def proj4(self):
        return self.sr.ExportToProj4()

    @property
    def sr(self):
        sr = SpatialReference()
        sr.ImportFromProj4(to_string(self.value))
        return sr

    def as_variable(self, with_proj4=True):
        from ocgis.variable.base import Variable
        var = Variable(name=self.name)
        if with_proj4:
            var.attrs['proj4'] = self.proj4
        return var

    def convert_to_empty(self):
        self._is_empty = True

    def extract(self):
        return self

    def load(self, *args, **kwargs):
        """Compatibility with variable."""
        pass

    def write_to_rootgrp(self, rootgrp, with_proj4=False):
        """
        Write the coordinate system to an open netCDF file.

        :param rootgrp: An open netCDF dataset object for writing.
        :type rootgrp: :class:`netCDF4.Dataset`
        :param bool with_proj4: If ``True``, write the PROJ.4 string to the coordinate system variable in an attribute
         called "proj4".
        :returns: The netCDF variable object created to hold the coordinate system metadata.
        :rtype: :class:`netCDF4.Variable`
        """
        variable = rootgrp.createVariable(self.name, 'S1')
        if with_proj4:
            variable.proj4 = self.proj4
        return variable

    def write(self, *args, **kwargs):
        write_mode = kwargs.pop('write_mode', MPIWriteMode.NORMAL)
        with_proj4 = kwargs.pop('with_proj4', False)
        # Fill operations set values on variables. Coordinate system variables have no inherent values constructed only
        # from attributes.
        if write_mode != MPIWriteMode.FILL:
            return self.write_to_rootgrp(*args, with_proj4=with_proj4)

    @classmethod
    def get_wrap_action(cls, state_src, state_dst):
        """
        :param int state_src: The wrapped state of the source dataset. (:class:`~ocgis.constants.WrappedState`)
        :param int state_dst: The wrapped state of the destination dataset. (:class:`~ocgis.constants.WrappedState`)
        :returns: The wrapping action to perform on ``state_src``. (:class:`~ocgis.constants.WrapAction`)
        :rtype: int
        :raises: NotImplementedError, ValueError
        """

        possible = [WrappedState.WRAPPED, WrappedState.UNWRAPPED, WrappedState.UNKNOWN]
        has_issue = None
        if state_src not in possible:
            has_issue = 'source'
        if state_dst not in possible:
            has_issue = 'destination'
        if has_issue is not None:
            msg = 'The wrapped state on "{0}" is not recognized.'.format(has_issue)
            raise ValueError(msg)

        # the default action is to do nothing.
        ret = None
        # if the wrapped state of the destination is unknown, then there is no appropriate wrapping action suitable for
        # the source.
        if state_dst == WrappedState.UNKNOWN:
            ret = None
        # if the destination is wrapped and src is unwrapped, then wrap the src.
        elif state_dst == WrappedState.WRAPPED:
            if state_src == WrappedState.UNWRAPPED:
                ret = WrapAction.WRAP
        # if the destination is unwrapped and the src is wrapped, the source needs to be unwrapped.
        elif state_dst == WrappedState.UNWRAPPED:
            if state_src == WrappedState.WRAPPED:
                ret = WrapAction.UNWRAP
        else:
            raise NotImplementedError(state_dst)
        return ret

    def get_wrapped_state(self, target, comm=None):
        """
        :param field: Return the wrapped state of a field. This function only checks grid centroids and geometry
         exteriors. Bounds/corners on the grid are excluded.
        :type field: :class:`ocgis.new_interface.field.OcgField`
        """
        # TODO: Wrapped state should operate on the x-coordinate variable vectors or geometries only.
        from ocgis.collection.field import OcgField
        from ocgis.spatial.grid import GridXY

        comm, rank, size = get_standard_comm_state(comm)

        # If this is not a geographic coordinate system, wrapped state is undefined.
        if not self.is_geographic:
            ret = None
        else:
            if isinstance(target, OcgField):
                if target.grid is not None:
                    target = target.grid
                else:
                    target = target.geom

            if target is None:
                raise ValueError('Target has no spatial information to evaluate.')
            elif target.is_empty:
                ret = None
            elif isinstance(target, GridXY):
                ret = self._get_wrapped_state_from_array_(target.x.value)
            else:
                stops = (WrappedState.WRAPPED, WrappedState.UNWRAPPED)
                ret = WrappedState.UNKNOWN
                geoms = target.value.flat
                for geom in geoms:
                    flag = self._get_wrapped_state_from_geometry_(geom)
                    if flag in stops:
                        ret = flag
                        break

        rets = comm.gather(ret)
        if rank == 0:
            rets = set(rets)
            if WrappedState.WRAPPED in rets:
                ret = WrappedState.WRAPPED
            elif WrappedState.UNWRAPPED in rets:
                ret = WrappedState.UNWRAPPED
            else:
                ret = list(rets)[0]
        else:
            ret = None
        ret = comm.bcast(ret)

        return ret

    def wrap_or_unwrap(self, action, target):
        from ocgis.variable.geom import GeometryVariable
        from ocgis.spatial.grid import GridXY

        if action not in (WrapAction.WRAP, WrapAction.UNWRAP):
            raise ValueError('"action" not recognized: {}'.format(action))

        if action == WrapAction.WRAP:
            attr = 'wrap'
        else:
            attr = 'unwrap'

        if isinstance(target, GeometryVariable):
            w = GeometryWrapper()
            func = getattr(w, attr)
            target_value = target.get_value()
            for idx, target_geom in iter_array(target_value, use_mask=True, return_value=True,
                                               mask=target.get_mask()):
                target_value.__setitem__(idx, func(target_geom))
        elif isinstance(target, GridXY):
            ca = CoordinateArrayWrapper()
            func = getattr(ca, attr)
            func(target.x.value)
            target.remove_bounds()
            if target.has_allocated_point:
                getattr(target.get_point(), attr)()
            if target.has_allocated_polygon:
                getattr(target.get_polygon(), attr)()
        else:
            raise NotImplementedError(target)

    @classmethod
    def _get_wrapped_state_from_array_(cls, arr):
        """
        :param arr: Input n-dimensional array.
        :type arr: :class:`numpy.ndarray`
        :returns: Wrapped state enumeration value from :class:`~ocgis.constants.WrappedState`.
        :rtype: int
        """

        gt_m180 = arr > constants.MERIDIAN_180TH
        lt_pm = arr < 0

        if np.any(lt_pm):
            ret = WrappedState.WRAPPED
        elif np.any(gt_m180):
            ret = WrappedState.UNWRAPPED
        else:
            ret = WrappedState.UNKNOWN

        return ret

    @classmethod
    def _get_wrapped_state_from_geometry_(cls, geom):
        """
        :param geom: The input geometry.
        :type geom: :class:`~shapely.geometry.point.Point`, :class:`~shapely.geometry.point.Polygon`,
         :class:`~shapely.geometry.multipoint.MultiPoint`, :class:`~shapely.geometry.multipolygon.MultiPolygon`
        :returns: A string flag. See class level ``_flag_*`` attributes for values.
        :rtype: str
        :raises: NotImplementedError
        """

        if isinstance(geom, BaseMultipartGeometry):
            itr = geom
        else:
            itr = [geom]

        app = np.array([])
        for element in itr:
            if isinstance(element, Point):
                element_arr = [np.array(element)[0]]
            elif isinstance(element, Polygon):
                element_arr = np.array(element.exterior.coords)[:, 0]
            else:
                raise NotImplementedError(type(element))
            app = np.append(app, element_arr)

        return cls._get_wrapped_state_from_array_(app)

    @staticmethod
    def _place_prime_meridian_array_(arr):
        """
        Replace any 180 degree values with the value of :attribute:`ocgis.constants.MERIDIAN_180TH`.

        :param arr: The target array to modify inplace.
        :type arr: :class:`numpy.array`
        :rtype: boolean :class:`numpy.array`
        """
        from ocgis import constants

        # find the values that are 180
        select = arr == 180
        # replace the values that are 180 with the constant value
        np.place(arr, select, constants.MERIDIAN_180TH)
        # return the mask used for the replacement
        return select


class Spherical(CoordinateReferenceSystem):
    """
    A spherical model of the Earth's surface with equivalent semi-major and semi-minor axes.

    :param semi_major_axis: The radius of the spherical model. The default value is taken from the PROJ.4 (v4.8.0)
     source code (src/pj_ellps.c).
    :type semi_major_axis: float
    """

    def __init__(self, semi_major_axis=6370997.0):
        value = {'proj': 'longlat', 'towgs84': '0,0,0,0,0,0,0', 'no_defs': '', 'a': semi_major_axis,
                 'b': semi_major_axis}
        CoordinateReferenceSystem.__init__(self, value=value, name='latitude_longitude')
        self.major_axis = semi_major_axis


class WGS84(CoordinateReferenceSystem):
    """
    A representation of the Earth using the WGS84 datum (i.e. EPSG code 4326).
    """

    def __init__(self):
        CoordinateReferenceSystem.__init__(self, epsg=4326, name='latitude_longitude')


class CFCoordinateReferenceSystem(CoordinateReferenceSystem):
    __metaclass__ = abc.ABCMeta

    # If False, no attempt to read projection coordinates will be made. they will be set to a None default.
    _find_projection_coordinates = True

    # Alternative grid mapping names to check. Should be a tuple in subclasses.
    _fuzzy_grid_mapping_names = None

    # Default map parameter values.
    map_parameters_defaults = {}

    def __init__(self, **kwds):
        self.projection_x_coordinate = kwds.pop('projection_x_coordinate', None)
        self.projection_y_coordinate = kwds.pop('projection_y_coordinate', None)

        # Always provide a default name for the CF-based coordinate systems.
        name = kwds.pop('name', self.grid_mapping_name)

        check_keys = kwds.keys()
        for key in kwds.keys():
            check_keys.remove(key)
        if len(check_keys) > 0:
            raise ValueError('The keyword parameter(s) "{0}" was/were not provided.')

        self.map_parameters_values = kwds
        crs = {'proj': self.proj_name}
        for k in self.map_parameters.keys():
            if k in self.iterable_parameters:
                v = getattr(self, self.iterable_parameters[k])(kwds[k])
                crs.update(v)
            else:
                try:
                    crs.update({self.map_parameters[k]: kwds[k]})
                except KeyError:
                    # Attempt to load any default map parameter values.
                    crs.update({self.map_parameters[k]: self.map_parameters_defaults[k]})

        super(CFCoordinateReferenceSystem, self).__init__(value=crs, name=name)

    @abc.abstractproperty
    def grid_mapping_name(self):
        str

    @abc.abstractproperty
    def iterable_parameters(self):
        dict

    @abc.abstractproperty
    def map_parameters(self):
        dict

    @abc.abstractproperty
    def proj_name(self):
        str

    def format_standard_parallel(self, value):
        if isinstance(value, np.ndarray):
            value = value.tolist()

        ret = {}
        try:
            it = iter(value)
        except TypeError:
            it = [value]
        for ii, v in enumerate(it, start=1):
            ret.update({self.map_parameters['standard_parallel'].format(ii): v})
        return ret

    @classmethod
    def get_fuzzy_names(cls):
        ret = list(get_iter(cls.grid_mapping_name))
        if cls._fuzzy_grid_mapping_names is not None:
            ret += list(get_iter(cls._fuzzy_grid_mapping_names))
        return tuple(ret)

    @classmethod
    def load_from_metadata(cls, var, meta, strict=True):

        def _get_projection_coordinate_(target, meta):
            key = 'projection_{0}_coordinate'.format(target)
            for k, v in meta['variables'].items():
                if 'standard_name' in v['attributes']:
                    if v['attributes']['standard_name'] == key:
                        return k
            raise ProjectionCoordinateNotFound(key)

        r_var = meta['variables'][var]
        try:
            # Look for the grid_mapping attribute on the target variable.
            r_grid_mapping = meta['variables'][r_var['attributes']['grid_mapping']]
        except KeyError:
            # Attempt to match the class's grid mapping name across variables if strictness allows.
            if not strict:
                r_grid_mapping = None
                fuzzy_names = cls.get_fuzzy_names()
                for var_meta in meta['variables'].values():
                    if var_meta['name'] in fuzzy_names:
                        r_grid_mapping = var_meta
                        break
                if r_grid_mapping is None:
                    raise ProjectionDoesNotMatch
            else:
                raise ProjectionDoesNotMatch
        try:
            grid_mapping_name = r_grid_mapping['attributes']['grid_mapping_name']
        except KeyError:
            raise ProjectionDoesNotMatch
        if grid_mapping_name != cls.grid_mapping_name:
            raise ProjectionDoesNotMatch

        # get the projection coordinates if not turned off by class attribute.
        if cls._find_projection_coordinates:
            pc_x, pc_y = [_get_projection_coordinate_(target, meta) for target in ['x', 'y']]
        else:
            pc_x, pc_y = None, None

        # this variable name is used by the netCDF converter
        # meta['grid_mapping_variable_name'] = r_grid_mapping['name']

        kwds = r_grid_mapping['attributes'].copy()
        kwds.pop('grid_mapping_name', None)
        kwds['projection_x_coordinate'] = pc_x
        kwds['projection_y_coordinate'] = pc_y

        # add the correct name to the coordinate system
        kwds['name'] = r_grid_mapping['name']

        cls._load_from_metadata_finalize_(kwds, var, meta)

        return cls(**kwds)

    @classmethod
    def _load_from_metadata_finalize_(cls, kwds, var, meta):
        pass

    def write_to_rootgrp(self, rootgrp, with_proj4=False):
        variable = super(CFCoordinateReferenceSystem, self).write_to_rootgrp(rootgrp, with_proj4=with_proj4)
        variable.grid_mapping_name = self.grid_mapping_name
        for k, v in self.map_parameters_values.iteritems():
            if v is None:
                v = ''
            setattr(variable, k, v)
        return variable


class CFSpherical(Spherical, CFCoordinateReferenceSystem):
    grid_mapping_name = 'latitude_longitude'
    iterable_parameters = None
    map_parameters = None
    proj_name = None

    def __init__(self, *args, **kwargs):
        self.map_parameters_values = {}
        Spherical.__init__(self, *args, **kwargs)

    @classmethod
    def load_from_metadata(cls, var, meta):
        r_grid_mapping = meta['variables'][var]['attributes'].get('grid_mapping')
        r_grid_mapping_name = meta['variables'][var]['attributes'].get('grid_mapping_name')
        if cls.grid_mapping_name in (r_grid_mapping, r_grid_mapping_name):
            return cls()
        else:
            raise ProjectionDoesNotMatch


class CFWGS84(CFSpherical, WGS84):
    def __init__(self, *args, **kwargs):
        self.map_parameters_values = {}
        WGS84.__init__(self, *args, **kwargs)


class CFAlbersEqualArea(CFCoordinateReferenceSystem):
    grid_mapping_name = 'albers_conical_equal_area'
    iterable_parameters = {'standard_parallel': 'format_standard_parallel'}
    map_parameters = {'standard_parallel': 'lat_{0}',
                      'longitude_of_central_meridian': 'lon_0',
                      'latitude_of_projection_origin': 'lat_0',
                      'false_easting': 'x_0',
                      'false_northing': 'y_0'}
    proj_name = 'aea'


class CFLambertConformal(CFCoordinateReferenceSystem):
    grid_mapping_name = 'lambert_conformal_conic'
    iterable_parameters = {'standard_parallel': 'format_standard_parallel'}
    map_parameters = {'standard_parallel': 'lat_{0}',
                      'longitude_of_central_meridian': 'lon_0',
                      'latitude_of_projection_origin': 'lat_0',
                      'false_easting': 'x_0',
                      'false_northing': 'y_0',
                      'units': 'units'}
    map_parameters_defaults = {'false_easting': 0,
                               'false_northing': 0}
    proj_name = 'lcc'

    @classmethod
    def _load_from_metadata_finalize_(cls, kwds, var, meta):
        kwds['units'] = meta['variables'][kwds['projection_x_coordinate']]['attributes'].get('units')


class CFPolarStereographic(CFCoordinateReferenceSystem):
    grid_mapping_name = 'polar_stereographic'
    map_parameters = {'standard_parallel': 'lat_ts',
                      'latitude_of_projection_origin': 'lat_0',
                      'straight_vertical_longitude_from_pole': 'lon_0',
                      'false_easting': 'x_0',
                      'false_northing': 'y_0',
                      'scale_factor': 'k_0'}
    proj_name = 'stere'
    iterable_parameters = {}

    def __init__(self, *args, **kwds):
        if 'scale_factor' not in kwds:
            kwds['scale_factor'] = 1.0
        super(CFPolarStereographic, self).__init__(*args, **kwds)


class CFNarccapObliqueMercator(CFCoordinateReferenceSystem):
    grid_mapping_name = 'transverse_mercator'
    map_parameters = {'latitude_of_projection_origin': 'lat_0',
                      'longitude_of_central_meridian': 'lonc',
                      'scale_factor_at_central_meridian': 'k_0',
                      'false_easting': 'x_0',
                      'false_northing': 'y_0',
                      'alpha': 'alpha'}
    proj_name = 'omerc'
    iterable_parameters = {}

    def __init__(self, *args, **kwds):
        if 'alpha' not in kwds:
            kwds['alpha'] = 360
        super(CFNarccapObliqueMercator, self).__init__(*args, **kwds)


class CFRotatedPole(CFCoordinateReferenceSystem):
    grid_mapping_name = 'rotated_latitude_longitude'
    iterable_parameters = {}
    map_parameters = {'grid_north_pole_longitude': None, 'grid_north_pole_latitude': None}
    proj_name = 'omerc'
    _find_projection_coordinates = False
    _fuzzy_grid_mapping_names = ('rotated_pole', 'rotated_lat_lon')
    _template = '+proj=ob_tran +o_proj=latlon +o_lon_p={lon_pole} +o_lat_p={lat_pole} +lon_0=180 +ellps={ellps}'

    def __init__(self, *args, **kwds):
        super(CFRotatedPole, self).__init__(*args, **kwds)

        # this is the transformation string used in the proj operation
        self._trans_proj = self._template.format(lon_pole=kwds['grid_north_pole_longitude'],
                                                 lat_pole=kwds['grid_north_pole_latitude'],
                                                 ellps=constants.PROJ4_ROTATED_POLE_ELLPS)

    def update_with_rotated_pole_transformation(self, grid, inverse=False):
        """
        :type spatial: :class:`ocgis.interface.base.dimension.spatial.SpatialDimension`
        :param bool inverse: If ``True``, this is an inverse transformation.
        :rtype: :class:`ocgis.interface.base.dimension.spatial.SpatialDimension`
        """
        assert grid.crs.is_geographic or isinstance(grid.crs, CFRotatedPole)

        grid.remove_bounds()
        grid.expand()

        rlon, rlat = get_lonlat_rotated_pole_transform(grid.x.value.flatten(), grid.y.value.flatten(),
                                                       self._trans_proj, inverse=inverse)

        grid.x.set_value(rlon.reshape(*grid.shape))
        grid.y.set_value(rlat.reshape(*grid.shape))

    def write_to_rootgrp(self, rootgrp, **kwargs):
        """
        .. note:: See :meth:`~ocgis.interface.base.crs.CoordinateReferenceSystem.write_to_rootgrp`.
        """

        variable = super(CFRotatedPole, self).write_to_rootgrp(rootgrp, **kwargs)
        if kwargs.get(KeywordArguments.WITH_PROJ4, False):
            variable.proj4 = ''
            variable.proj4_transform = self._trans_proj
        return variable


def get_lonlat_rotated_pole_transform(lon, lat, transform, inverse=False, is_vectorized=False):
    """
    Transform longitude and latitude coordinates to/from their rotated pole representation.

    :param lon: Vector of longitude coordinates.
    :param lat: Vector of latitude coordinates.
    :param str transform: The PROJ.4 transform string.
    :param inverse: If ``True``, coordinates are in spherical longitude/latitude and should be transformed to rotated
     pole.
    :return: A tuple with the first element being transformed longitude and the second element being transformed
     latitude.
    :rtype: tuple
    """

    import csv
    import subprocess

    class ProjDialect(csv.excel):
        lineterminator = '\n'
        delimiter = '\t'

    f = tempfile.NamedTemporaryFile()
    try:
        writer = csv.writer(f, dialect=ProjDialect)
        if is_vectorized:
            for lon_idx, lat_idx in itertools.product(*[range(lon.shape[0]), range(lat.shape[0])]):
                writer.writerow([lon[lon_idx], lat[lat_idx]])
        else:
            for idx in range(lon.shape[0]):
                writer.writerow([lon[idx], lat[idx]])
        f.flush()
        cmd = transform.split(' ')
        cmd.append(f.name)
        if inverse:
            program = 'invproj'
        else:
            program = 'proj'
        cmd = [program, '-f', '"%.6f"', '-m', '57.2957795130823'] + cmd
        capture = subprocess.check_output(cmd)
    finally:
        f.close()

    coords = capture.split('\n')
    new_coords = []

    for ii, coord in enumerate(coords):
        coord = coord.replace('"', '')
        coord = coord.split('\t')
        try:
            coord = map(float, coord)
        # likely empty string
        except ValueError:
            if coord[0] == '':
                continue
            else:
                raise
        new_coords.append(coord)

    rlon_rlat = np.array(new_coords)
    rlon = rlon_rlat[:, 0]
    rlat = rlon_rlat[:, 1]

    return rlon, rlat