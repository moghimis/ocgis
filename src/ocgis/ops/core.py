from ocgis.base import AbstractOcgisObject
from ocgis.conv.meta import MetaOCGISConverter
from ocgis.ops.engine import OperationsEngine
from ocgis.ops.interpreter import OcgInterpreter
from ocgis.ops.parms.base import AbstractParameter
from ocgis.ops.parms.definition import *
from ocgis.variable.crs import CFRotatedPole, WGS84, Spherical, CFWGS84


class OcgOperations(AbstractOcgisObject):
    """
    Entry point for all OCGIS operations.

    :param dataset: A ``dataset`` is the target file(s) or object(s) containing data to process.
    :type dataset: :class:`~ocgis.RequestDatasetCollection`, :class:`~ocgis.RequestDataset`/:class:`~ocgis.Field`, or
     sequence of :class:`~ocgis.RequestDataset`/:class:`~ocgis.Field` objects
    :param spatial_operation: The geometric operation to be performed.
    :type spatial_operation: str
    :param geom: The selection geometry(s) used for the spatial subset. If ``None``, selection defaults to entire
     spatial domain.
    :type geom: list of dict, list of float, str
    :param str geom_select_sql_where: A string suitable for insertion into a SQL WHERE statement. See http://www.gdal.org/ogr_sql.html
     for documentation (section titled "WHERE").
    :param geom_select_uid: The unique identifiers of specific geometries contained in the geometry datasets. Geometries
     having these unique identifiers will be used for subsetting.
    :type geom_select_uid: sequence of integers
    :param str geom_uid: If provided, use this as the unique geometry identifier. If ``None``, use the value of
     :attr:`~ocgis.env.DEFAULT_GEOM_UID`. If that is not present, generate a one-based unique identifier with that name.
    :param aggregate: If ``True``, dataset geometries are aggregated to coincident
     selection geometries.
    :type aggregate: bool
    :param calc: Calculations to be performed on the dataset subset.
    :type calc: list of dictionaries or string-based function
    :param calc_grouping: Temporal grouping to apply for calculations.
    :type calc_grouping: list(str), int , None
    :param calc_raw: If ``True``, perform calculations on the "raw" data regardless of ``aggregation`` flag.
    :type calc_raw: bool
    :param abstraction: The geometric abstraction to use for the dataset geometries. If `None` (the default), use the
     highest order geometry available.
    :type abstraction: str
    :param snippet: If ``True``, return a data "snippet" composed of the first time point, first level (if applicable),
     and the entire spatial domain.
    :type snippet: bool
    :param backend: The processing backend to use.
    :type backend: str
    :param prefix: The output prefix to prepend to any output data filename.
    :type prefix: str
    :param output_format: The desired output format.
    :type output_format: str
    :param agg_selection: If ``True``, the selection geometry will be aggregated prior to any spatial operations.
    :type agg_selection: bool
    :param vector_wrap: If `True`, keep any vector output on a -180 to 180 longitudinal domain.
    :type vector_wrap: bool
    :param allow_empty: If `True`, do not raise an exception in the case of an empty geometric selection.
    :type allow_empty: bool
    :param dir_output: The output directory to which any disk format folders are written. If the directory does not
     exist, an exception will be raised. This will override :attr:`env.DIR_OUTPUT`.
    :type dir_output: str
    :param slice: A five-element list to use for slicing the input data. This will override any other susetting.
    :type slice: list
    :param format_time: If ``True`` (the default), attempt to coerce time values to datetime stamps. If ``False``, pass
     values through without a coercion attempt. This only affects :class:`~ocgis.RequestDataset` objects.
    :type format_time: bool
    :param calc_sample_size: If `True`, calculate statistical sample sizes for calculations.
    :type calc_sample_size: bool
    :param output_crs: If provided, all output geometries will be projected to match the provided CRS.
    :type output_crs: :class:`ocgis.crs.CoordinateReferenceSystem`
    :param search_radius_mult: This value is multiplied by the target data's spatial resolution to determine the buffer
     radius for point selection geometries.
    :type search_radius_mult: float
    :param interpolate_spatial_bounds: If True and no bounds are available, attempt to interpolate bounds from
     centroids.
    :type interpolate_spatial_bounds: bool
    :param bool add_auxiliary_files: If ``True``, create a new directory and add metadata and other informational files
     in addition to the converted file. If ``False``, write the target file only to :attr:`dir_output` and do not create
     a new directory.
    :param function callback: A function taking two parameters: ``percent_complete`` and ``message``.
    :param time_range: Upper and lower bounds for time dimension subsetting. If `None`, return all time points. Using
     this argument will overload all :class:`~ocgis.RequestDataset` ``time_range`` values.
    :type time_range: [:class:`datetime.datetime`, :class:`datetime.datetime`]
    :param time_region: A dictionary with keys of 'month' and/or 'year' and values as sequences corresponding to target
     month and/or year values. Empty region selection for a key may be set to `None`. Using this argument will overload
     all :class:`~ocgis.RequestDataset` ``time_region`` values.
    :type time_region: dict
    :param time_subset_func: See :meth:`ocgis.interface.base.dimension.temporal.TemporalDimension.get_subset_by_function`
     for usage instructions.
    :type time_subset_func: :class:`FunctionType`
    :param level_range: Upper and lower bounds for level dimension subsetting. If `None`, return all levels. Using this
     argument will overload all :class:`~ocgis.RequestDataset` ``level_range`` values.
    :type level_range: [int/float, int/float]
    :param conform_units_to: Destination units for conversion. If this parameter is set, then the :mod:`cfunits` module
     must be installed. Setting this parameter will override conformed units set on ``dataset`` objects.
    :type conform_units_to: str or :class:`cfunits.Units`
    :param bool select_nearest: If ``True``, the nearest geometry to the centroid of the current selection geometry is
     returned. This is useful when subsetting by a point, and it is preferred to not return all geometries within the
     selection radius.
    :param regrid_destination: If provided, regrid ``dataset`` objects using ESMPy to this destination grid. If a string
     is provided, then the :class:`~ocgis.RequestDataset` with the corresponding name will be selected as the
     destination. Please see :ref:`esmpy-regridding` for an overview.
    :type regrid_destination: str, :class:`~ocgis.interface.base.field.Field` or :class:`~ocgis.interface.base.dimension.spatial.SpatialDimension`
    :param dict regrid_options: Overload the default keywords for regridding. Dictionary elements must map to the names
     of keyword arguments for :meth:`~ocgis.regrid.base.iter_regridded_fields`. If this is left as ``None``, then the
     default keyword values are used. Please see :ref:`esmpy-regridding` for an overview.
    :param bool melted: If ``None``, default to :attr:`ocgis.env.MELTED`. If ``False`` (the default), variable names are
     individual columns in tabular output formats (i.e. ``'csv'``). If ``True``, all variable values will be collected
     under a single value column.
    :param dict output_format_options: A dictionary of output-specific format options.
    :param str spatial_wrapping: If ``"wrap"`` or ``"unwrap"``, wrap or unwrap the spatial coordinates if the associated
     coordinate system is a wrappable coordinate system like spherical latitude/longitude.
    :param bool spatial_reorder: If ``True``, reorder wrapped coordinates such that the longitude values are in
     ascending order. Reordering assumes the first row of longitude coordinates are representative of the other
     longitude coordinate rows. Bounds and corners will be removed in the event of a reorder. Only applies to spherical
     coordinate systems.
    :param bool optimized_bbox_subset: If ``True``, only perform the bounding box subset ignoring other subsetting
     procedures such as spatial operations on geometry objects using a spatial index.
    """

    def __init__(self, dataset=None, spatial_operation='intersects', geom=None, geom_select_sql_where=None,
                 geom_select_uid=None, geom_uid=None, aggregate=False, calc=None, calc_grouping=None,
                 calc_raw=False, abstraction='auto', snippet=False, backend='ocg', prefix=None, output_format='numpy',
                 agg_selection=False, select_ugid=None, vector_wrap=True, allow_empty=False, dir_output=None,
                 slice=None, file_only=False, format_time=True, calc_sample_size=False, search_radius_mult=2.0,
                 output_crs=None, interpolate_spatial_bounds=False, add_auxiliary_files=True, optimizations=None,
                 callback=None, time_range=None, time_region=None, time_subset_func=None, level_range=None,
                 conform_units_to=None, select_nearest=False, regrid_destination=None, regrid_options=None,
                 melted=False, output_format_options=None, spatial_wrapping=None, spatial_reorder=False,
                 optimized_bbox_subset=False):

        # Tells "__setattr__" to not perform global validation until all values are initially set.
        self._is_init = True

        self.dataset = Dataset(dataset)
        self.spatial_operation = SpatialOperation(spatial_operation)
        self.aggregate = Aggregate(aggregate)
        self.calc_sample_size = CalcSampleSize(calc_sample_size)
        self.calc = Calc(calc)
        self.calc_grouping = CalcGrouping(calc_grouping)
        self.calc_raw = CalcRaw(calc_raw)
        self.abstraction = Abstraction(abstraction)
        self.snippet = Snippet(snippet)
        self.backend = Backend(backend)
        self.prefix = Prefix(prefix or env.PREFIX)
        self.output_format = OutputFormat(output_format)
        self.output_format_options = OutputFormatOptions(output_format_options)
        self.agg_selection = AggregateSelection(agg_selection, output_format=self.output_format)
        self.geom_select_sql_where = GeomSelectSqlWhere(geom_select_sql_where)
        self.geom_select_uid = GeomSelectUid(geom_select_uid or select_ugid)
        self.geom_uid = GeomUid(geom_uid)
        self.geom = Geom(geom, select_ugid=self.geom_select_uid, geom_uid=self.geom_uid,
                         geom_select_sql_where=self.geom_select_sql_where, union=self.agg_selection)
        self.vector_wrap = VectorWrap(vector_wrap)
        self.allow_empty = AllowEmpty(allow_empty)
        self.dir_output = DirOutput(dir_output or env.DIR_OUTPUT)
        self.slice = Slice(slice)
        self.file_only = FileOnly(file_only)
        self.output_crs = OutputCRS(output_crs)
        self.search_radius_mult = SearchRadiusMultiplier(search_radius_mult)
        self.format_time = FormatTime(format_time)
        self.interpolate_spatial_bounds = InterpolateSpatialBounds(interpolate_spatial_bounds)
        self.add_auxiliary_files = AddAuxiliaryFiles(add_auxiliary_files)
        self.optimizations = Optimizations(optimizations)
        self.optimized_bbox_subset = OptimizedBoundingBoxSubset(optimized_bbox_subset)
        self.callback = Callback(callback)
        self.time_range = TimeRange(time_range)
        self.time_region = TimeRegion(time_region)
        self.time_subset_func = TimeSubsetFunction(time_subset_func)
        self.level_range = LevelRange(level_range)
        self.conform_units_to = ConformUnitsTo(conform_units_to)
        self.select_nearest = SelectNearest(select_nearest)
        self.regrid_destination = RegridDestination(init_value=regrid_destination, dataset=self._get_object_('dataset'))
        self.regrid_options = RegridOptions(regrid_options)
        self.melted = Melted(init_value=env.MELTED or melted)
        self.spatial_wrapping = SpatialWrapping(spatial_wrapping)
        self.spatial_reorder = SpatialReorder(spatial_reorder)

        # These values are left in to perhaps be added back in at a later date.
        self.output_grouping = None

        # Initial values have been set and global validation should now occur when any parameters are updated.
        self._is_init = False
        self._update_dependents_()
        self._validate_()

    def __str__(self):
        msg = ['{0}('.format(self.__class__.__name__)]
        for key, value in self.as_dict().iteritems():
            if key == 'geom' and value is not None:
                value = 'custom geometries'
            msg.append('{0}, '.format(self._get_object_(key)))
        msg.append(')')
        msg = ''.join(msg)
        return msg

    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)
        if isinstance(attr, AbstractParameter):
            ret = attr.value
        else:
            ret = attr
        return ret

    def __setattr__(self, name, value):
        if isinstance(value, AbstractParameter):
            object.__setattr__(self, name, value)
        else:
            try:
                attr = object.__getattribute__(self, name)
                attr.value = value
            except AttributeError:
                object.__setattr__(self, name, value)
        if self._is_init is False:
            self._update_dependents_()
            self._validate_()

    def get_base_request_size(self):
        """
        Return the estimated request size in kilobytes. This is the estimated size
        of the requested data not the returned data product.

        :returns: Dictionary with keys ``'total'`` and ``'variables'``. The ``'variables'``
         key maps a variable's alias to its estimated value and dimension sizes, shapes, and
         data types.
        :return type: dict

        >>> ret = ops.get_base_request_size()
        {'total':555.,
         'variables':{
                      'tas':{
                             'value':{'kb':500.,'shape':(1,300,1,10,10),'dtype':dtype('float64')},
                             'temporal':{'kb':50.,'shape':(300,),'dtype':dtype('float64')},
                             'level':{'kb':o.,'shape':None,'dtype':None},
                             'realization':{'kb':0.,'shape':None,'dtype':None},
                             'row':{'kb':2.5,'shape':(10,),'dtype':dtype('float64')},
                             'col':{'kb':2.5,'shape':(10,),'dtype':dtype('float64')}
                             }
                      }
        }
        """

        if self.regrid_destination is not None:
            msg = 'Base request size not supported with a regrid destination.'
            raise DefinitionValidationError(RegridDestination, msg)

        def _get_kb_(dtype, elements):
            nbytes = np.array([1], dtype=dtype).nbytes
            return float((elements * nbytes) / 1024.0)

        def _get_zero_or_kb_(dimension):
            ret = {'shape': None, 'kb': 0.0, 'dtype': None}
            if dimension is not None:
                try:
                    ret['dtype'] = dimension.dtype
                    ret['shape'] = dimension.shape
                    ret['kb'] = _get_kb_(dimension.dtype, dimension.shape[0])
                # dtype may not be available, check if it is the realization dimension. this is often not associated
                # with a variable.
                except ValueError:
                    if dimension.axis != 'R':
                        raise
            return ret

        ops_size = deepcopy(self)
        subset = OperationsEngine(ops_size, request_base_size_only=True)
        ret = dict(variables={})
        for coll in subset:
            for row in coll.get_iter_melted():
                elements = reduce(lambda x, y: x * y, row['field'].shape)
                kb = _get_kb_(row['variable'].dtype, elements)
                ret['variables'][row['variable_alias']] = {}
                ret['variables'][row['variable_alias']]['value'] = {'shape': row['field'].shape, 'kb': kb,
                                                                    'dtype': row['variable'].dtype}
                ret['variables'][row['variable_alias']]['realization'] = _get_zero_or_kb_(row['field'].realization)
                ret['variables'][row['variable_alias']]['temporal'] = _get_zero_or_kb_(row['field'].temporal)
                ret['variables'][row['variable_alias']]['level'] = _get_zero_or_kb_(row['field'].level)
                ret['variables'][row['variable_alias']]['row'] = _get_zero_or_kb_(row['field'].spatial.grid.row)
                ret['variables'][row['variable_alias']]['col'] = _get_zero_or_kb_(row['field'].spatial.grid.col)

        total = 0.0
        for v in ret.itervalues():
            for v2 in v.itervalues():
                for v3 in v2.itervalues():
                    total += float(v3['kb'])
        ret['total'] = total
        return ret

    def get_meta(self):
        meta_converter = MetaOCGISConverter(self)
        rows = meta_converter.get_rows()
        return '\n'.join(rows)

    def as_dict(self):
        """:rtype: dict"""

        ret = {}
        for value in self.__dict__.itervalues():
            try:
                ret.update({value.name: value.value})
            except AttributeError:
                pass
        return ret

    def execute(self):
        """Execute the request using the selected backend.
        
        :rtype: Path to an output file/folder or dictionary composed of :class:`ocgis.driver.collection.AbstractCollection` objects.
        """
        interp = OcgInterpreter(self)
        return interp.execute()

    def _get_object_(self, name):
        return object.__getattribute__(self, name)

    def _update_dependents_(self):
        # the select_ugid parameter must always connect to the geometry selection
        geom = self._get_object_(Geom.name)
        svalue = self._get_object_(GeomSelectUid.name)._value
        geom.select_ugid = svalue

    def _validate_(self):
        ocgis_lh(logger='operations', msg='validating operations')

        def _raise_(msg, obj=OutputFormat):
            e = DefinitionValidationError(obj, msg)
            ocgis_lh(exc=e, logger='operations')

        # Assert the driver may be written to the appropriate output format.
        dataset = self._get_object_(Dataset.name)
        for rd in dataset.iter_by_type(RequestDataset):
            rd.driver.validate_ops(self)

        # Validate the converter.
        converter_klass = get_converter(self.output_format)
        converter_klass.validate_ops(self)

        # No clipping with regridding.
        if self.regrid_destination is not None:
            if self.spatial_operation == 'clip':
                msg = 'Regridding not allowed with spatial "clip" operation.'
                raise DefinitionValidationError(SpatialOperation, msg)

        # Collect unique coordinate systems. None is returned if one is not parsable.
        projections = []
        for element in dataset:
            if not any([_ == element.crs for _ in projections]):
                projections.append(element.crs)

        # if there is not output CRS and projections differ, raise an exception. however, it is okay to have data with
        # different projections in the numpy output.
        if len(projections) > 1 and self.output_format != 'numpy':  # @UndefinedVariable
            if self.output_crs is None:
                _raise_('Dataset coordinate reference systems must be equivalent if no output CRS is chosen.',
                        obj=OutputCRS)

        # clip and/or aggregation operations may not be written back to CFRotatedPole at this time. hence, the output
        # crs must be set to CFWGS84.
        if CFRotatedPole in map(type, projections):
            if self.output_crs is not None and not isinstance(self.output_crs, WGS84):
                msg = ('{0} data may only be written to the same coordinate system (i.e. "output_crs=None") '
                       'or {1}.').format(CFRotatedPole.__name__, CFWGS84.__name__)
                _raise_(msg, obj=OutputCRS)
            if self.aggregate or self.spatial_operation == 'clip':
                msg = (
                    '{0} data if clipped or spatially averaged must be written to ' '{1}. The "output_crs" is being updated to {2}.').format(
                    CFRotatedPole.__name__, CFWGS84.__name__, CFWGS84.__name__)
                ocgis_lh(level=logging.WARN, msg=msg, logger='operations')
                self._get_object_('output_crs')._value = CFWGS84()

        # Only WGS84 coordinate system may be written to GeoJSON.
        if self.output_format == constants.OUTPUT_FORMAT_GEOJSON:
            msg = 'Only data with a WGS84 or Spherical projection may be written to GeoJSON.'
            if self.output_crs is not None:
                if self.output_crs != WGS84() and self.output_crs != Spherical():
                    _raise_(msg)
            else:
                if any([not (element == WGS84() or element == Spherical()) for element in projections
                        if element is not None]):
                    _raise_(msg)

        # snippet only relevant for subsetting not operations with a calculation or time region
        if self.snippet:
            if self.calc is not None:
                msg = 'Snippets are not implemented for calculations. Apply a limiting time range for faster responses.'
                _raise_(msg, obj=Snippet)
            for rd in dataset.iter_by_type(RequestDataset):
                if rd.time_region is not None:
                    _raise_('Snippets are not implemented for time regions.', obj=Snippet)

        # no slicing with a geometry - can easily lead to extent errors
        if self.slice is not None:
            assert self.geom is None

        # file only operations only valid for netCDF and calculations.
        if self.file_only:
            if self.output_format != 'nc':
                _raise_('Only netCDF-CF may be written with file_only as "True".', obj=FileOnly)
            if self.calc is None:
                _raise_('File only outputs are only relevant for computations.', obj=FileOnly)

        # validate any calculations against the operations object. if the calculation is a string eval function do not
        # validate.
        if self.calc is not None:
            if self._get_object_('calc')._is_eval_function:
                if self.calc_grouping is not None:
                    msg = 'Calculation groups are not applicable for string function expressions.'
                    _raise_(msg, obj=CalcGrouping)
            else:
                for c in self.calc:
                    c['ref'].validate(self)