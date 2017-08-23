import datetime
import os

import six
import logging
import numpy as np
import ocgis
from ocgis import RequestDataset
from ocgis import env, vm
from ocgis.calc.base import AbstractMultivariateFunction, AbstractKeyedOutputFunction
from ocgis.calc.engine import CalculationEngine
from ocgis.calc.eval_function import MultivariateEvalFunction
from ocgis.constants import HeaderName
from ocgis.constants import MPIWriteMode, DimensionName
from ocgis.conv.base import _write_dataset_identifier_file_, _write_source_meta_
from ocgis.constants import KeywordArgument
from ocgis.conv.base import AbstractCollectionConverter
from ocgis.driver.nc import DriverNetcdf
from ocgis.exc import DefinitionValidationError
from ocgis.util.logging_ocgis import ocgis_lh
from ocgis.vmachine.mpi import MPI_RANK
from ocgis.ops.engine import get_data_model
from ocgis.environment import get_dtype

class NcConverter(AbstractCollectionConverter):
    """
    .. note:: Accepts all parameters to :class:`~ocgis.conv.base.AbstractCollectionConverter`.

    :param options: (``=None``) The following options are valid:

    +------------------------+----------------------------------------------------------------------------------------------------------------------------------------+
    | Option                 | Description                                                                                                                            |
    +========================+========================================================================================================================================+
    | data_model             | The netCDF data model: http://unidata.github.io/netcdf4-python/#netCDF4.Dataset.                                                       |
    +------------------------+----------------------------------------------------------------------------------------------------------------------------------------+
    | variable_kwargs        | Dictionary of keyword parameters to use for netCDF variable creation. See: http://unidata.github.io/netcdf4-python/#netCDF4.Variable.  |
    +------------------------+----------------------------------------------------------------------------------------------------------------------------------------+
    | unlimited_to_fixedsize | If ``True``, convert the unlimited dimension to fixed size. Only applies to time and level dimensions.                                 |
    +------------------------+----------------------------------------------------------------------------------------------------------------------------------------+
    | geom_dim               | The name of the dimension storing aggregated (unioned) outputs. Only applies when ``aggregate is True``.                               |
    +------------------------+----------------------------------------------------------------------------------------------------------------------------------------+


    >>> options = {'data_model': 'NETCDF4_CLASSIC'}
    >>> options = {'variable_kwargs': {'zlib': True, 'complevel': 4}}

    :type options: str
    """
    _ext = 'nc'

    @property
    def _variable_kwargs(self):
        try:
            ret = self.ops.output_format_options.get('variable_kwargs', {})
        except AttributeError:
            # Likely "ops" or "output_format_options" is None.
            ret = {}
        return ret

    @classmethod
    def validate_ops(cls, ops):
        from ocgis.ops.parms.definition import OutputFormat

        def _raise_(msg, ocg_arugument=OutputFormat):
            raise DefinitionValidationError(ocg_arugument, msg)

        # We can only write one request dataset to netCDF.
        len_ops_dataset = len(list(ops.dataset))
        if len_ops_dataset > 1 and ops.calc is None:
            msg = 'Data packages (i.e. more than one RequestDataset) may not be written to netCDF. There are ' \
                  'currently {dcount} RequestDatasets. Note, this is different than a multifile dataset.'
            msg = msg.format(dcount=len_ops_dataset)
            _raise_(msg, OutputFormat)
        # We can write multivariate functions to netCDF.
        else:
            if ops.calc is not None and len_ops_dataset > 1:
                # Count the occurrences of these classes in the calculation list.
                klasses_to_check = [AbstractMultivariateFunction, MultivariateEvalFunction]
                multivariate_checks = []
                for klass in klasses_to_check:
                    for calc in ops.calc:
                        multivariate_checks.append(issubclass(calc['ref'], klass))
                if sum(multivariate_checks) != 1:
                    msg = ('Data packages (i.e. more than one RequestDataset) may not be written to netCDF. '
                           'There are currently {dcount} RequestDatasets. Note, this is different than a '
                           'multifile dataset.'.format(dcount=len(ops.dataset)))
                    _raise_(msg, OutputFormat)
                else:
                    # There is a multivariate calculation and this requires multiple request datasets.
                    pass

        # Clipped data which creates an arbitrary geometry may not be written to netCDF.
        if ops.spatial_operation != 'intersects' and not ops.aggregate:
            msg = ('Only "intersects" spatial operation allowed for netCDF output. Arbitrary geometries may not '
                   'currently be written.')
            _raise_(msg, OutputFormat)

        # Calculations on raw values are not relevant as not aggregation can occur anyway.
        if ops.calc is not None:
            if ops.calc_raw:
                msg = 'Calculations must be performed on original values (i.e. calc_raw=False) for netCDF output.'
                _raise_(msg)
            # No keyed output functions to netCDF.
            if CalculationEngine._check_calculation_members_(ops.calc, AbstractKeyedOutputFunction):
                msg = 'Keyed function output may not be written to netCDF.'
                _raise_(msg)

        # Re-organize the collections following a discrete geometry model if aggregate is True

        if ops.aggregate and len(ops.geom) < 1:
            msg = 'If aggregate is True than a geometry must be provided for netCDF output. '
            _raise_(msg, OutputFormat)

    def _preformatting(self, i, coll):
        """
        Modify in place the collections so they can be saved as discrete
        geometries along a new spatial dimension.

        """

        # Size of spatial dimension
        ncoll = len(self.ops.geom)

        udim = DimensionName.UNIONED_GEOMETRY

        ugids = coll.properties.keys()
        assert len(ugids) == 1
        ugid = ugids[0]

        # Geometry centroid location
        lon, lat = coll.geoms[ugid].centroid.xy

        for field in coll.iter_fields():

            lon_attrs = field.x.attrs.copy()
            lat_attrs = field.y.attrs.copy()
            xn = field.x.name
            yn = field.y.name

            # Removed for now. It'd be nice to find an elegant way to retain those.
            field.remove_variable(xn)
            field.remove_variable(yn)

            # Create new lon and lat variables
            field.add_variable(
                ocgis.Variable(xn,
                               value=lon,
                               dimensions=(udim,),
                               attrs=dict(lon_attrs, **{
                                   'long_name': 'Centroid longitude'})
                               )
            )

            field.add_variable(
                ocgis.Variable(yn,
                               value=lat,
                               dimensions=(udim,),
                               attrs=dict(lat_attrs, **{
                                   'long_name': 'Centroid latitude'})
                               )
            )

            if 'ocgis_spatial_mask' in field:
                # Remove the spatial_mask and replace by new one.
                field.remove_variable('ocgis_spatial_mask')

            grid = ocgis.Grid(field[xn], field[yn], abstraction='point',
                              crs=field.crs, parent=field)
            grid.set_mask([[False, ]])
            field.set_grid(grid)

            # Geometry variables from the geom properties dict
            dm = get_data_model(self.ops)

            # Some dtypes are not supported by netCDF3. Use the netCDF4
            # data model to avoid these issues.
            for key, val in coll.properties[ugid].items():
                if np.issubdtype(type(val), int):
                    dt = get_dtype('int', dm)
                elif np.issubdtype(type(val), float):
                    dt = get_dtype('float', dm)
                else:
                    dt = 'auto'

                # There is no metadata for those yet, but it could be passed
                # using the output_format_options keyword.
                field.add_variable(
                    ocgis.Variable(key,
                                   value=[val, ],
                                   dtype=dt,
                                   dimensions=(udim,)))

            # ------------------ Dimension update ------------------------ #
            # Modify the dimensions for the number of geometries
            gdim = field.dimensions[udim]
            gdim.set_size(ncoll)

            for var in field.iter_variables_by_dimensions([gdim]):
                d = var.dimensions_dict[udim]
                d.bounds_local = (i, i + 1)
            # ------------------------------------------------------------ #

            # CF-Conventions
            # Options for cf-role are timeseries_id, profile_id, trajectory_id
            gid = field[HeaderName.ID_GEOMETRY]
            gid.attrs['cf_role'] = 'timeseries_id'

            # Name of spatial dimension
            if self.options.get('geom_dim', None):
                gdim.set_name(self.options.get('geom_dim', None))

            return coll


    def _get_file_format_(self):
        file_format = set()
        # Use the data model passed to the constructor.
        if self.options.get('data_model') is not None:
            ret = self.options['data_model']
        else:
            # If no operations are present, use the default data model.
            if self.ops is None:
                ret = env.NETCDF_FILE_FORMAT
            else:
                # If operations are available, check the request datasets and determine the best format for output.
                for rd in self.ops.dataset:
                    # Only request dataset will have a possible output format.
                    if not isinstance(rd, RequestDataset):
                        continue
                    try:
                        rr = rd.metadata['file_format']
                    except KeyError:
                        # Likely a shapefile request dataset which does not have an origin netcdf data format.
                        if not isinstance(rd.driver, DriverNetcdf):
                            continue
                        else:
                            raise
                    if isinstance(rr, six.string_types):
                        tu = [rr]
                    else:
                        tu = rr
                    file_format.update(tu)
                if len(file_format) > 1:
                    raise ValueError('Multiple file formats found: {0}'.format(file_format))
                else:
                    try:
                        ret = list(file_format)[0]
                    except IndexError:
                        # Likely all field objects in the dataset. Use the default netCDF data model.
                        ret = env.NETCDF_FILE_FORMAT
        return ret

    def _write_archetype_(self, arch, write_kwargs, variable_kwargs):
        """
        Write a field to a netCDF dataset object.

        :param arch: The field to write.
        :type arch: :class:`ocgis.new_interface.field.Field`
        :param dict write_kwargs: Dictionary of parameters needed for the write.
        :param dict variable_kwargs: Optional keyword parameters to pass to the creation of netCDF4 variable objects.
         See http://unidata.github.io/netcdf4-python/#netCDF4.Variable.
        """
        # Append to the history attribute.
        history_str = '\n{dt} UTC ocgis-{release}'.format(dt=datetime.datetime.utcnow(), release=ocgis.__release__)
        if self.ops is not None:
            history_str += ': {0}'.format(self.ops)
        original_history_str = arch.attrs.get('history', '')
        arch.attrs['history'] = original_history_str + history_str

        if self.ops.aggregate:
            arch.attrs['featureType'] = 'timeSeries'

        # Pull in dataset and variable keyword arguments.
        unlimited_to_fixedsize = self.options.get(KeywordArgument.UNLIMITED_TO_FIXED_SIZE, False)
        variable_kwargs[KeywordArgument.UNLIMITED_TO_FIXED_SIZE] = unlimited_to_fixedsize
        write_kwargs[KeywordArgument.VARIABLE_KWARGS] = variable_kwargs
        write_kwargs[KeywordArgument.DATASET_KWARGS] = {KeywordArgument.FORMAT: self._get_file_format_()}

        # This is the output path. The driver handles MPI writing.
        path = write_kwargs.get(KeywordArgument.PATH)

        # Write the field.
        arch.write(path, **write_kwargs)

    def _write_coll_(self, ds, coll):
        """
        Write a spatial collection to an open netCDF4 dataset object.

        :param ds: An open dataset object.
        :type ds: :class:`netCDF4.Dataset`
        :param coll: The collection containing data to write.
        :type coll: :class:`~ocgis.SpatialCollection`
        """

        # Get the target field from the collection.
        arch = coll.archetype_field
        """:type arch: :class:`ocgis.Field`"""

        self._write_archetype_(arch, ds, self._variable_kwargs)

class NcRegionConverter(NcConverter):
    """
    Save multiple SpatialCollections in a unique netCDF file along a geometry
    dimension.
    """
    _ext = 'nc'

    def write(self):
        ocgis_lh('starting write method', self._log, logging.DEBUG)

        # Indicates if user geometries should be written to file.
        write_ugeom = False

        ncoll = len(self.ops.geom)

        build = True
        for i, coll in enumerate(self):
            ugids = coll.properties.keys()
            assert len(ugids) == 1
            ugid = ugids[0]

            # Geometry centroid location
            lon, lat = coll.geoms[ugid].centroid.xy

            for field in coll.iter_fields():

                lon_attrs = field.x.attrs.copy()
                lat_attrs = field.y.attrs.copy()
                xn = field.x.name
                yn = field.y.name

                # Removed for now. It'd be nice to find an elegant way to retain those.
                field.remove_variable(xn)
                field.remove_variable(yn)

                # Create new lon and lat variables
                field.add_variable(
                    ocgis.Variable(xn,
                                   value=lon,
                                   dimensions=(DimensionName.UNIONED_GEOMETRY,),
                                   attrs=dict(lon_attrs, **{'long_name':'Centroid longitude'})
                                   )
                )


                field.add_variable(
                    ocgis.Variable(yn,
                                   value=lat,
                                   dimensions=(DimensionName.UNIONED_GEOMETRY,),
                                   attrs=dict(lat_attrs, **{'long_name':'Centroid latitude'})
                                   )
                )


                if 'ocgis_spatial_mask' in field:
                    # Remove the spatial_mask and replace by new one.
                    field.remove_variable('ocgis_spatial_mask')


                grid = ocgis.Grid(field[xn], field[yn], abstraction='point',
                  crs=field.crs, parent=field)
                grid.set_mask([[False,]])
                field.set_grid(grid)

                # Geometry variables from the geom properties dict
                dm = get_data_model(self.ops)

                # Some dtypes are not supported by netCDF3. Use the netCDF4
                # data model to avoid these issues.
                for key, val in coll.properties[ugid].items():
                    if np.issubdtype(type(val), int):
                        dt = get_dtype('int', dm)
                    elif np.issubdtype(type(val), float):
                        dt = get_dtype('float', dm)
                    else:
                        dt='auto'

                    # There is no metadata for those yet, but it could be passed
                    # using the output_format_options keyword.
                    field.add_variable(
                        ocgis.Variable(key,
                                       value=[val,],
                                       dtype=dt,
                                       dimensions=(DimensionName.UNIONED_GEOMETRY,)))

                # ------------------ Dimension update ------------------------ #
                # Modify the dimensions for the number of geometries
                gdim = field.dimensions[DimensionName.UNIONED_GEOMETRY]
                gdim.set_size(ncoll)

                for var in field.iter_variables_by_dimensions([gdim]):
                    d = var.dimensions_dict[DimensionName.UNIONED_GEOMETRY]
                    d.bounds_local = (i, i+1)
                # ------------------------------------------------------------ #

                # CF-Conventions
                # Options for cf-role are timeseries_id, profile_id, trajectory_id
                gid = field[HeaderName.ID_GEOMETRY]
                gid.attrs['cf_role'] = 'timeseries_id'

            # Path to the output object.
            # I needed to put it here because _write_archetype pops it, so it's not available after the first loop.
            f = {KeywordArgument.PATH: self.path}

            # This will be changed to "write" if we are on the build loop.
            write_mode = MPIWriteMode.APPEND

            if build:
                # During a build loop, create the file and write the first series of records. Let the drivers determine
                # the appropriate write modes for handling parallelism.
                write_mode = None

                # Write the user geometries if selected and there is one present on the incoming collection.
                if self._add_ugeom and coll.has_container_geometries:
                    write_ugeom = True

                if write_ugeom:
                    if vm.rank == 0:
                        # The output file name for the user geometries.
                        ugid_shp_name = self.prefix + '_ugid.shp'
                        if self._add_ugeom_nest:
                            ugeom_fiona_path = os.path.join(self._get_or_create_shp_folder_(), ugid_shp_name)
                        else:
                            ugeom_fiona_path = os.path.join(self.outdir, ugid_shp_name)
                    else:
                        ugeom_fiona_path = None

                build = False

            f[KeywordArgument.WRITE_MODE] = write_mode
            self._write_coll_(f, coll)

            if write_ugeom:
                with vm.scoped(SubcommName.UGEOM_WRITE, [0]):
                    if not vm.is_null:
                        for subset_field in list(coll.children.values()):
                            subset_field.write(ugeom_fiona_path, write_mode=write_mode, driver=DriverVector)

        # The metadata and dataset descriptor files may only be written if OCGIS operations are present.
        ops = self.ops
        if ops is not None and self.add_auxiliary_files and MPI_RANK == 0:
            # Add OCGIS metadata output if requested.
            if self.add_meta:
                ocgis_lh('adding OCGIS metadata file', 'conv', logging.DEBUG)
                from ocgis.conv.meta import MetaOCGISConverter

                lines = MetaOCGISConverter(ops).write()
                out_path = os.path.join(self.outdir, self.prefix + '_' + MetaOCGISConverter._meta_filename)
                with open(out_path, 'w') as f:
                    f.write(lines)

            # Add the dataset descriptor file if requested.
            if self._add_did_file:
                ocgis_lh('writing dataset description (DID) file', 'conv', logging.DEBUG)
                path = os.path.join(self.outdir, self.prefix + '_did.csv')
                _write_dataset_identifier_file_(path, ops)

            # Add source metadata if requested.
            if self._add_source_meta:
                ocgis_lh('writing source metadata file', 'conv', logging.DEBUG)
                path = os.path.join(self.outdir, self.prefix + '_source_metadata.txt')
                _write_source_meta_(path, ops)

        # Return the internal path unless overloaded by subclasses.
        ret = self._get_return_()

        return ret
