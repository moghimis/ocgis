from ocgis.calc import base
import numpy as np
from ocgis import constants


class FrequencyPercentile(base.AbstractUnivariateSetFunction,base.AbstractParameterizedFunction):
    key = 'freq_perc'
    parms_definition = {'percentile':float}
    description = 'The percentile value along the time axis. See: http://docs.scipy.org/doc/numpy-dev/reference/generated/numpy.percentile.html.'
    dtype = constants.np_float
    standard_name = 'frequency_percentile'
    long_name = 'Frequency Percentile'
    
    def calculate(self,values,percentile=None):
        '''
        :param percentile: Percentile to compute.
        :type percentile: float on the interval [0,100]
        '''
        ret = np.percentile(values,percentile,axis=0)
        return(ret)


class Max(base.AbstractUnivariateSetFunction):
    description = 'Max value for the series.'
    key = 'max'
    dtype = constants.np_float
    standard_name = 'max'
    long_name = 'max'
    
    def calculate(self,values):
        return(np.ma.max(values,axis=0))


class Min(base.AbstractUnivariateSetFunction):
    description = 'Min value for the series.'
    key = 'min'
    dtype = constants.np_float
    standard_name = 'min'
    long_name = 'Min'
    
    def calculate(self,values):
        return(np.ma.min(values,axis=0))

    
class Mean(base.AbstractUnivariateSetFunction):
    description = 'Compute mean value of the set.'
    key = 'mean'
    dtype = constants.np_float
    standard_name = 'mean'
    long_name = 'Mean'
    
    def calculate(self,values):
        return(np.ma.mean(values,axis=0))
    
    
class Median(base.AbstractUnivariateSetFunction):
    description = 'Compute median value of the set.'
    key = 'median'
    dtype = constants.np_float
    standard_name = 'median'
    long_name = 'median'
    
    def calculate(self,values):
        return(np.ma.median(values,axis=0))
    
    
class StandardDeviation(base.AbstractUnivariateSetFunction):
    description = 'Compute standard deviation of the set.'
    key = 'std'
    dtype = constants.np_float
    standard_name = 'standard_deviation'
    long_name = 'Standard Deviation'
    
    def calculate(self,values):
        return(np.ma.std(values,axis=0))
