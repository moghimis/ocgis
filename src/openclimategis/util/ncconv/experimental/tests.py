import unittest
from ocg_dataset import OcgDataset
from shapely.geometry.point import Point
import datetime
from datetime import date
from shapely import wkt
from util.ncconv.experimental.ocg_converter import *
from util.ncconv.experimental.wrappers import multipolygon_operation
import os
from osgeo import ogr
import warnings
from util.ncconv.experimental.ocg_dataset import SubOcgDataset
from util.ncconv.experimental.ocg_stat import OcgStat
from shapely.geometry.multipolygon import MultiPolygon
import numpy as np
from util.ncconv.experimental.helpers import timing
from shapely.geometry.polygon import Polygon
import itertools
from util.ncconv.experimental.ocg_dataset.todb import PgBackend
from util.ncconv.experimental.ocg_dataset.stat import SubOcgStat
import time

verbose = False

def convert_wkt(f):
    def wrapf(*args,**kwds):
        return(wkt.loads(f(*args,**kwds)))
    return(wrapf)


class ShpIterator(object):
    
    def __init__(self,path):
        assert(os.path.exists(path))
        self.path = path
        
    def iter_features(self,fields,lyridx=0,geom='geom',skiperrors=False):
        ds = ogr.Open(self.path)
        try:
            lyr = ds.GetLayerByIndex(lyridx)
            lyr.ResetReading()
            for feat in lyr:
                ## get the values
                values = []
                for field in fields:
                    try:
                        values.append(feat.GetField(field))
                    except:
                        try:
                            if skiperrors is True:
                                warnings.warn('Error in GetField("{0}")'.format(field))
                            else:
                                raise
                        except ValueError:
                            msg = 'Illegal field requested in GetField("{0}")'.format(field)
                            raise ValueError(msg)
#                values = [feat.GetField(field) for field in fields]
                attrs = dict(zip(fields,values))
                ## get the geometry
                attrs.update({geom:feat.GetGeometryRef().ExportToWkt()})
                yield attrs
        finally:
            ds.Destroy()


class TestData(object):
#    nc_path = '/home/bkoziol/git/OpenClimateGIS/bin/climate_data/wcrp_cmip3/pcmdi.ipcc4.bccr_bcm2_0.1pctto2x.run1.monthly.cl_A1_1.nc'
#    nc_opts = dict(rowbnds_name='lat_bnds',
#                   colbnds_name='lon_bnds',
#                   calendar='gregorian',
#                   time_units='days since 1800-1-1 00:00:0.0',
#                   level_name='lev')
    
#    nc_path = '/home/bkoziol/git/OpenClimateGIS/bin/climate_data/maurer/bccr_bcm2_0.1.sresa2.monthly.Prcp.1951.nc'
#    nc_var_name = 'Prcp'
#    nc_opts = dict(rowbnds_name='bounds_latitude',
#                   colbnds_name='bounds_longitude',
#                   calendar='proleptic_gregorian',
#                   time_units='days since 1950-01-01 00:00:0.0')
    
    nc_path = 'http://cida.usgs.gov/qa/thredds/dodsC/maurer/monthly'
    nc_opts = dict(rowbnds_name='bounds_latitude',
                   colbnds_name='bounds_longitude',
                   calendar='proleptic_gregorian',
                   time_units='days since 1950-01-01 00:00:0.0')
    nc_var_name = 'sresa1b_miroc3-2-medres_2_Prcp'
    
    shp_path = '/home/bkoziol/git/OpenClimateGIS/bin/shp/state_boundaries.shp'
    
    def simple_polygon(self):
        pt = Point(200,0.0)
        return(pt.buffer(8,1))
    
    @convert_wkt
    def nebraska(self):
        wkt = "POLYGON ((-101.407393290830782 40.001003364718585,-102.051535291430682 39.998918364716637,-102.047545291426971 40.342644365036762,-102.047620291427037 40.431077365119123,-102.046031291425564 40.697319365367079,-102.046992291426449 40.743130365409741,-102.047739291427149 40.998071365647171,-102.621257291961285 41.000214365649171,-102.652271291990161 40.998124365647222,-103.38295629267067 41.000316365649262,-103.57231629284702 40.999648365648639,-104.051705293293494 41.003211365651964,-104.054012293295642 41.388085366010401,-104.055500293297015 41.564222366174441,-104.053615293295266 41.69821836629923,-104.053513293295168 41.999815366580123,-104.056219293297687 42.614669367152743,-104.056199293297666 43.003062367514467,-103.501464292781037 42.998618367510332,-103.005875292319487 42.999354367511017,-102.78838429211693 42.99530336750724,-102.086701291463442 42.989887367502192,-101.231737290667184 42.986843367499361,-100.198142289704577 42.99109536750332,-99.532790289084915 42.992335367504474,-99.253971288825255 42.992389367504529,-98.497651288120878 42.991778367503954,-98.457444288083423 42.937160367453089,-98.39120428802174 42.920135367437233,-98.31033928794642 42.881794367401525,-98.167826287813696 42.839571367362204,-98.144869287792318 42.835794367358687,-98.123117287772061 42.820223367344184,-98.121820287770845 42.808360367333137,-98.033140287688255 42.769192367296654,-97.995144287652877 42.766812367294442,-97.963558287623457 42.773690367300844,-97.929477287591723 42.792324367318201,-97.88994128755489 42.831271367354475,-97.888659287553708 42.855807367377324,-97.818643287488499 42.866587367387368,-97.797028287468365 42.849597367371544,-97.772186287445223 42.846164367368345,-97.725250287401522 42.858008367379369,-97.685752287364735 42.836837367359657,-97.634970287317444 42.861285367382422,-97.57065428725754 42.847990367370045,-97.506132287197445 42.860136367381358,-97.483159287176051 42.857157367378576,-97.457263287151932 42.850443367372328,-97.389306287088644 42.867433367388152,-97.311414287016106 42.861771367382879,-97.271457286978887 42.850014367371926,-97.243189286952557 42.851826367373619,-97.224443286935099 42.841202367363721,-97.211831286923356 42.812573367337059,-97.161422286876416 42.798619367324065,-97.130469286847585 42.773923367301066,-97.01513928674018 42.759542367287665,-96.979593286707072 42.758313367286526,-96.970003286698145 42.752065367280707,-96.97786928670547 42.727308367257649,-96.970773286698858 42.721147367251916,-96.908234286640607 42.73169936726174,-96.810140286549256 42.704084367236021,-96.810437286549529 42.681341367214841,-96.799344286539196 42.67001936720429,-96.722658286467777 42.668592367202962,-96.6990602864458 42.657715367192836,-96.694596286441652 42.64116336717742,-96.715273286460899 42.621907367159487,-96.714059286459772 42.612302367150541,-96.636672286387693 42.550731367093199,-96.629294286380826 42.522693367067092,-96.605467286358632 42.507236367052691,-96.58475328633935 42.518287367062982,-96.547215286304393 42.520499367065042,-96.494701286255477 42.488459367035205,-96.439394286203964 42.489240367035933,-96.396074286163625 42.467401367015597,-96.397890286165321 42.441793366991746,-96.4176282861837 42.414777366966582,-96.411761286178233 42.380918366935049,-96.424175286189794 42.349279366905584,-96.389781286157771 42.328789366886497,-96.368700286138136 42.298023366857848,-96.342881286114078 42.282081366843002,-96.332658286104561 42.260307366822722,-96.337708286109262 42.22952236679405,-96.3635122861333 42.214042366779637,-96.352165286122727 42.168185366736921,-96.285123286060298 42.123452366695261,-96.265483286041999 42.04889736662583,-96.238725286017086 42.028438366606778,-96.236093286014636 42.001258366581467,-96.202842285983664 41.996615366577139,-96.185217285967255 41.980685366562298,-96.147328285931962 41.966254366548867,-96.145870285930599 41.924907366510354,-96.159970285943743 41.904151366491021,-96.135623285921056 41.862620366452347,-96.076417285865915 41.791469366386082,-96.099321285887257 41.752975366350228,-96.09977128588767 41.731563366330292,-96.08555728587443 41.704987366305538,-96.122202285908557 41.694913366296156,-96.120264285906757 41.684094366286082,-96.099306285887238 41.654680366258688,-96.11130728589842 41.599006366206837,-96.080835285870037 41.576000366185411,-96.091936285880379 41.563145366173437,-96.085840285874696 41.537522366149574,-96.050172285841484 41.524335366137294,-96.004592285799035 41.536663366148773,-95.99396528578913 41.528103366140805,-95.996688285791663 41.511517366125361,-96.013451285807278 41.492994366108107,-96.006897285801173 41.481954366097824,-95.953185285751147 41.47238736608891,-95.935065285734282 41.462381366079597,-95.940056285738919 41.394805366016655,-95.942895285741571 41.340077365965691,-95.88910728569148 41.301389365929658,-95.897591285699377 41.286863365916133,-95.911202285712051 41.308469365936254,-95.930230285729778 41.302056365930284,-95.910981285711841 41.22524536585874,-95.922250285722342 41.20785436584255,-95.91610028571661 41.194063365829706,-95.859198285663624 41.180537365817102,-95.859801285664176 41.16686536580437,-95.876685285679912 41.164202365801899,-95.858274285662759 41.109187365750657,-95.878804285681881 41.065871365710315,-95.859539285663942 41.035002365681564,-95.860897285665203 41.002650365651434,-95.83760328564351 40.974258365624991,-95.836541285642525 40.901108365556865,-95.834396285640523 40.87030036552818,-95.846435285651737 40.848332365507716,-95.851790285656719 40.792600365455812,-95.876616285679845 40.730436365397921,-95.767999285578682 40.643117365316598,-95.757546285568949 40.620904365295907,-95.767479285578204 40.589048365266237,-95.763412285574418 40.549707365229601,-95.737036285549848 40.532373365213459,-95.692066285507963 40.524129365205781,-95.687413285503638 40.561170365240272,-95.675693285492713 40.565835365244624,-95.662944285480847 40.558729365238008,-95.658060285476296 40.530332365211557,-95.684970285501365 40.512205365194674,-95.695361285511041 40.485338365169653,-95.636817285456516 40.396390365086816,-95.634185285454066 40.358800365051806,-95.616201285437313 40.346497365040349,-95.617933285438923 40.331418365026302,-95.645553285464644 40.32234636501785,-95.646827285465832 40.309109365005526,-95.595532285418059 40.309776365006144,-95.547137285372997 40.266215364965575,-95.476822285307506 40.226855364928923,-95.466636285298023 40.21325536491625,-95.46095228529272 40.173995364879687,-95.422476285256892 40.131743364840347,-95.392813285229266 40.115416364825137,-95.384542285221556 40.095362364806462,-95.403784285239482 40.080379364792506,-95.413764285248774 40.048111364762448,-95.390532285227138 40.043750364758395,-95.371244285209173 40.028751364744423,-95.345067285184797 40.024974364740906,-95.308697285150927 39.999407364717094,-95.329701285170486 39.992595364710752,-95.780700285590513 39.993489364711579,-96.001253285795926 39.995159364713139,-96.240598286018823 39.994503364712529,-96.45403828621761 39.994172364712213,-96.801420286541131 39.994476364712497,-96.908287286640657 39.996154364714066,-97.361912287063134 39.997380364715205,-97.816589287486579 39.999729364717396,-97.929588287591827 39.998452364716201,-98.264165287903424 39.998434364716189,-98.504479288127229 39.997129364714972,-98.720632288328545 39.998461364716213,-99.064747288649016 39.998338364716098,-99.178201288754678 39.999577364717254,-99.627859289173458 40.002987364720425,-100.180910289688526 40.000478364718091,-100.191111289698028 40.000585364718191,-100.735049290204614 39.99917236471687,-100.75485629022306 40.000198364717832,-101.322148290751386 40.001821364719341,-101.407393290830782 40.001003364718585))"
        return(wkt)
    
    @convert_wkt
    def iowa(self):
        wkt = 'POLYGON ((-91.120132281250022 40.705443365374641,-91.129303281258558 40.682189365352983,-91.162644281289616 40.656352365328921,-91.215060281338424 40.643859365317283,-91.262211281382349 40.639587365313304,-91.375762281488093 40.60348036527968,-91.411271281521167 40.573012365251302,-91.413026281522804 40.548034365228041,-91.382255281494139 40.528538365209883,-91.37494628148734 40.503697365186753,-91.385551281497214 40.447294365134226,-91.372908281485437 40.403032365092997,-91.385909281497547 40.392405365083107,-91.418968281528336 40.386919365077993,-91.448747281556066 40.371946365064048,-91.477038281582409 40.391012365081806,-91.490314281594777 40.390806365081616,-91.500377281604145 40.405160365094986,-91.527691281629586 40.410169365099648,-91.529607281631371 40.435086365122856,-91.538846281639977 40.441288365128628,-91.533208281634728 40.455441365141809,-91.579383281677735 40.463760365149554,-91.586028281683923 40.484519365168893,-91.616860281712633 40.504873365187848,-91.622536281717927 40.532903365213954,-91.692081281782691 40.551677365231434,-91.689959281780716 40.581202365258932,-91.71697628180587 40.593435365270324,-91.741711281828913 40.609784365285549,-91.946370282019515 40.608266365284138,-92.193174282249373 40.60008836527652,-92.36151328240615 40.599576365276043,-92.646432282671498 40.591462365268484,-92.717815282737973 40.58966736526682,-93.100938283094791 40.584347365261863,-93.37027128334563 40.580491365258268,-93.562910283525042 40.580813365258571,-93.786303283733091 40.578448365256364,-94.018059283948929 40.574022365252247,-94.238392284154131 40.570966365249404,-94.485231284384014 40.574205365252418,-94.639876284528043 40.575744365253854,-94.920616284789503 40.57721836525522,-95.217428285065921 40.581892365259577,-95.382555285219709 40.584334365261853,-95.767479285578204 40.589048365266237,-95.757546285568949 40.620904365295907,-95.767999285578682 40.643117365316598,-95.876616285679845 40.730436365397921,-95.851790285656719 40.792600365455812,-95.846435285651737 40.848332365507716,-95.834396285640523 40.87030036552818,-95.836541285642525 40.901108365556865,-95.83760328564351 40.974258365624991,-95.860897285665203 41.002650365651434,-95.859539285663942 41.035002365681564,-95.878804285681881 41.065871365710315,-95.858274285662759 41.109187365750657,-95.876685285679912 41.164202365801899,-95.859801285664176 41.16686536580437,-95.859198285663624 41.180537365817102,-95.91610028571661 41.194063365829706,-95.922250285722342 41.20785436584255,-95.910981285711841 41.22524536585874,-95.930230285729778 41.302056365930284,-95.911202285712051 41.308469365936254,-95.897591285699377 41.286863365916133,-95.88910728569148 41.301389365929658,-95.942895285741571 41.340077365965691,-95.940056285738919 41.394805366016655,-95.935065285734282 41.462381366079597,-95.953185285751147 41.47238736608891,-96.006897285801173 41.481954366097824,-96.013451285807278 41.492994366108107,-95.996688285791663 41.511517366125361,-95.99396528578913 41.528103366140805,-96.004592285799035 41.536663366148773,-96.050172285841484 41.524335366137294,-96.085840285874696 41.537522366149574,-96.091936285880379 41.563145366173437,-96.080835285870037 41.576000366185411,-96.11130728589842 41.599006366206837,-96.099306285887238 41.654680366258688,-96.120264285906757 41.684094366286082,-96.122202285908557 41.694913366296156,-96.08555728587443 41.704987366305538,-96.09977128588767 41.731563366330292,-96.099321285887257 41.752975366350228,-96.076417285865915 41.791469366386082,-96.135623285921056 41.862620366452347,-96.159970285943743 41.904151366491021,-96.145870285930599 41.924907366510354,-96.147328285931962 41.966254366548867,-96.185217285967255 41.980685366562298,-96.202842285983664 41.996615366577139,-96.236093286014636 42.001258366581467,-96.238725286017086 42.028438366606778,-96.265483286041999 42.04889736662583,-96.285123286060298 42.123452366695261,-96.352165286122727 42.168185366736921,-96.3635122861333 42.214042366779637,-96.337708286109262 42.22952236679405,-96.332658286104561 42.260307366822722,-96.342881286114078 42.282081366843002,-96.368700286138136 42.298023366857848,-96.389781286157771 42.328789366886497,-96.424175286189794 42.349279366905584,-96.411761286178233 42.380918366935049,-96.4176282861837 42.414777366966582,-96.397890286165321 42.441793366991746,-96.396074286163625 42.467401367015597,-96.439394286203964 42.489240367035933,-96.480243286242015 42.51713036706191,-96.489337286250489 42.564028367105578,-96.500942286261292 42.573885367114762,-96.488498286249708 42.580480367120906,-96.512844286272369 42.629755367166794,-96.541165286298749 42.662405367197209,-96.563039286319125 42.668513367202891,-96.626540286378258 42.708354367239998,-96.640709286391456 42.748603367277482,-96.632980286384267 42.776835367303775,-96.600875286354366 42.799558367324934,-96.587645286342038 42.835381367358302,-96.573126286328517 42.834347367357338,-96.55621128631276 42.846660367368806,-96.537511286295356 42.896906367415596,-96.544263286301643 42.913866367431396,-96.514935286274323 42.952382367467266,-96.517148286276381 42.986458367498997,-96.499020286259494 43.012050367522832,-96.520010286279046 43.051508367559585,-96.47957328624139 43.061884367569249,-96.46209428622511 43.075582367582001,-96.460805286223916 43.087872367593448,-96.451505286215252 43.12630836762925,-96.473114286235372 43.209082367706337,-96.487245286248537 43.217909367714554,-96.558605286315 43.225489367721622,-96.566991286322803 43.23963336773479,-96.559567286315897 43.253263367747479,-96.570722286326273 43.263612367757119,-96.579131286334103 43.29007436778177,-96.540563286298195 43.307659367798145,-96.522894286281741 43.356966367844066,-96.52505328628375 43.384225367869448,-96.557708286314153 43.400727367884819,-96.589113286343405 43.435539367917244,-96.583796286338455 43.481920367960441,-96.598315286351976 43.499849367977134,-96.46045428622358 43.49971836797701,-96.061039285851606 43.498533367975909,-95.866912285670807 43.498944367976293,-95.464775285296284 43.499541367976846,-95.396558285232757 43.500334367977587,-94.920464284789361 43.499371367976693,-94.8598392847329 43.500030367977303,-94.455238284356085 43.498102367975505,-94.24678728416194 43.498948367976297,-93.97395028390784 43.50029836797755,-93.653699283609583 43.500762367977984,-93.500830283467224 43.500488367977731,-93.05438028305143 43.501457367978631,-93.027211283026134 43.501278367978465,-92.558008282589142 43.50025936797752,-92.453169282491515 43.499462367976776,-92.077532282141675 43.49915336797649,-91.730366281818348 43.499571367976877,-91.611099281707268 43.500626367977858,-91.223566281346351 43.500808367978024,-91.235903281357835 43.464684367944386,-91.210916281334576 43.424051367906543,-91.198243281322775 43.370513367856681,-91.17704828130303 43.353946367841253,-91.078498281211253 43.313297367803393,-91.066428281200004 43.280683367773022,-91.069052281202445 43.2578983677518,-91.161354281288411 43.147576367649052,-91.168571281295129 43.082888367588808,-91.159752281286913 43.081182367587218,-91.152214281279896 43.001316367512842,-91.139121281267705 42.925893367442598,-91.093428281225144 42.871440367391884,-91.082030281214543 42.783365367309855,-91.066168281199765 42.744913367274044,-90.999182281137379 42.707058367238787,-90.919409281063082 42.680677367214223,-90.892545281038068 42.678240367211956,-90.745610280901218 42.657001367192173,-90.694791280853892 42.63792836717441,-90.664380280825569 42.57139136711244,-90.639219280802138 42.555714367097842,-90.625707280789555 42.528562367072553,-90.638456280801421 42.509363367054675,-90.65189928081395 42.49470036704102,-90.648473280810748 42.475647367023271,-90.605955280771155 42.460564367009226,-90.563711280731809 42.421843366973164,-90.491171280664261 42.388791366942385,-90.441725280618201 42.360083366915646,-90.427809280605246 42.34064536689754,-90.418112280596219 42.263939366826108,-90.40730128058614 42.242661366806288,-90.367858280549413 42.210226366776084,-90.323730280508315 42.197337366764074,-90.231063280422006 42.159741366729065,-90.191702280385357 42.122710366694577,-90.176214280370928 42.120524366692536,-90.166776280362143 42.103767366676934,-90.168226280363484 42.061066366637164,-90.150663280347132 42.033453366611447,-90.142796280339809 41.983989366565382,-90.154645280350834 41.930802366515849,-90.195965280389316 41.806167366399769,-90.255438280444707 41.781769366377048,-90.305016280490889 41.756497366353514,-90.326157280510571 41.7227683663221,-90.341262280524646 41.649122366253508,-90.339476280522973 41.602831366210395,-90.348494280531384 41.586882366195546,-90.423135280600889 41.567305366177308,-90.435098280612038 41.543612366155244,-90.45512628063068 41.527579366140316,-90.54097528071064 41.526003366138852,-90.600838280766396 41.50961836612359,-90.658929280820487 41.462350366079562,-90.70835428086653 41.450093366068145,-90.780042280933287 41.44985236606793,-90.844284280993122 41.444652366063082,-90.949800281091385 41.421263366041302,-91.000842281138929 41.431112366050471,-91.027637281163877 41.423536366043422,-91.05593528119023 41.401407366022809,-91.073429281206529 41.334925365960892,-91.102496281233599 41.267848365898416,-91.101672281232823 41.231552365864616,-91.056466281190723 41.176290365813152,-91.018402281155275 41.165857365803433,-90.990485281129281 41.144404365783458,-90.957930281098953 41.104393365746191,-90.954794281096042 41.070397365714527,-90.960851281101682 40.950541365602902,-90.983419281122693 40.923965365578155,-91.049353281184096 40.879623365536858,-91.089050281221077 40.833767365494154,-91.092895281224656 40.761587365426934,-91.120132281250022 40.705443365374641))'
        return(wkt)
    
    @convert_wkt
    def vermont(self):
        wkt = 'POLYGON ((-73.25806026461467 42.746058367275111,-73.269275264625108 42.747481367276436,-73.29616926465016 42.803549367328657,-73.279583264634709 42.837103367359902,-73.27600526463138 42.940294367456005,-73.250071264607229 43.31085436780112,-73.238391264596345 43.512832367989226,-73.259984264616463 43.55938236803258,-73.291402264645725 43.575033368047158,-73.28173626463672 43.593187368064065,-73.29410426464824 43.619653368088706,-73.303534264657017 43.624714368093422,-73.363685264713041 43.614998368084372,-73.38811426473579 43.569143368041665,-73.418320264763921 43.582479368054095,-73.42296026476825 43.632114368100318,-73.370989264719839 43.714281368176842,-73.356669264706511 43.756558368216218,-73.358997264708677 43.778427368236578,-73.384740264732656 43.804508368260869,-73.375121264723688 43.885977368336739,-73.405334264751829 43.914807368363597,-73.417406264763073 43.988197368431941,-73.40825126475454 44.018222368459902,-73.43600026478039 44.04567936848548,-73.435215264779657 44.063897368502445,-73.40875726475501 44.106610368542221,-73.407865264754193 44.136227368569806,-73.382062264730152 44.172107368603221,-73.377332264725752 44.201247368630362,-73.305325264658691 44.260142368685209,-73.329788264681468 44.367390368785095,-73.299995264653731 44.405533368820613,-73.293319264647508 44.432853368846061,-73.334452264685808 44.544328368949877,-73.347812264698263 44.553971368958862,-73.371296264720129 44.579167368982326,-73.38182526472994 44.61980736902018,-73.370136264719051 44.634349369033721,-73.373097264721807 44.661276369058797,-73.358151264707885 44.680368369076575,-73.373158264721866 44.724236369117435,-73.326786264678674 44.799293369187339,-73.369054264718045 44.819118369205796,-73.382306264730389 44.847933369232635,-73.336414264687647 44.932604369311491,-73.350758264701 44.981973369357469,-73.344723264695375 45.006138369379975,-73.188546264549927 45.008486369382162,-72.547231263952654 45.005370369379264,-71.901868263351616 45.007340369381097,-71.505372262982348 45.013351369386697,-71.540927263015462 44.976563369352434,-71.516977262993166 44.94369636932182,-71.50636526298328 44.899671369280824,-71.575101263047287 44.816019369202913,-71.583501263055112 44.779197369168621,-71.631133263099471 44.741710369133706,-71.607678263077631 44.677862369074248,-71.588749263059995 44.650599369048855,-71.568027263040705 44.637446369036603,-71.55410226302773 44.596589368998551,-71.536791263011608 44.578931368982111,-71.592288263063296 44.55120336895628,-71.591441263062507 44.538874368944803,-71.575243263047426 44.52580536893263,-71.586619263058012 44.494537368903508,-71.61422326308373 44.474507368884858,-71.636554263104529 44.476731368886931,-71.647709263114919 44.469174368879891,-71.656399263123006 44.440137368852845,-71.676884263142085 44.42134236883534,-71.766570263225617 44.398248368813839,-71.797729263254624 44.384172368800726,-71.821197263276488 44.35036036876923,-71.83481626328917 44.344199368763498,-71.928361263376289 44.336112368755963,-71.938905263386104 44.32578636874635,-71.994433263437827 44.327548368747991,-72.035495263476065 44.299434368721805,-72.059566263498482 44.261494368686471,-72.044390263484345 44.234379368661223,-72.059282263498218 44.182176368612602,-72.044724263484667 44.156435368588632,-72.034920263475527 44.120746368555388,-72.049515263489127 44.100452368536494,-72.03244726347323 44.096099368532435,-72.034728263475358 44.08337436852058,-72.07691926351464 44.032040368472778,-72.085204263522357 44.008924368451247,-72.109909263545376 43.989229368432902,-72.112808263548075 43.976515368421062,-72.091711263528424 43.95799136840381,-72.11320426354844 43.939166368386282,-72.121649263556307 43.909217368358384,-72.170089263601412 43.878917368330164,-72.184836263615153 43.801690368258249,-72.206092263634943 43.764635368223736,-72.219123263647077 43.75069236821075,-72.260055263685203 43.73530036819642,-72.304040263726165 43.698530368162167,-72.333085263753219 43.597364368067957,-72.37349826379085 43.572374368044677,-72.394998263810876 43.517554367993625,-72.382515263799249 43.48462936796296,-72.396248263812041 43.410156367893606,-72.412139263826845 43.377125367862838,-72.397628263813331 43.351006367838515,-72.410231263825068 43.323404367812806,-72.402419263817791 43.307382367797885,-72.435598263848689 43.232253367727921,-72.452398263864339 43.156022367656917,-72.437605263850557 43.116270367619897,-72.443464263856015 43.079039367585224,-72.461752263873052 43.046504367554924,-72.457159263868775 42.999603367511241,-72.473341263883839 42.976143367489399,-72.504263263912634 42.965584367479565,-72.520217263927506 42.9516723674666,-72.524810263931784 42.91261436743023,-72.553428263958423 42.860643367381826,-72.53891726394491 42.807733367332553,-72.513068263920843 42.789259367315346,-72.507269263915447 42.768732367296224,-72.479322263889415 42.761588367289576,-72.462171263873444 42.746840367275837,-72.455770263867478 42.725852367256294,-72.922997264302623 42.73736436726702,-73.019695264392681 42.740396367269838,-73.25806026461467 42.746058367275111))'
        return(wkt)
        
    def ne_ia(self):
        return(MultiPolygon([self.nebraska(),self.iowa()]))
    
    def usa(self,check_extent=True,check_masked=True):
        if verbose: print('getting usa features...')
        itr = ShpIterator(self.shp_path)
        ocg_dataset = self.ocg_dataset
        polygons = []
        for feat in itr.iter_features(['STATE_ABBR']):
            geom = wkt.loads(feat['geom'])
            if not isinstance(geom,Polygon):
                for poly in geom:
                    polygons.append(poly)
            else:
                polygons.append(geom)
        if check_extent:
            if verbose: print('  checking extent...')
            polygons = filter(ocg_dataset.check_extent,polygons)
        if check_masked:
            if verbose: print('  checking masked...')
            keep = []
            for poly in polygons:
                if ocg_dataset.check_masked(self.nc_var_name,poly):
                    keep.append(poly)
            polygons = keep
        if verbose: print('  done.')
        return(polygons)
    
    @property
    def ocg_dataset(self):
        return(OcgDataset(self.nc_path,**self.nc_opts))
    
    @property
    @timing
    def ocg_opts(self):
        return(dict(union=True,
                    clip=True,
                    polygon=self.ne_ia(),
                    time_range=[datetime.datetime(1951,1,1),
                                datetime.datetime(1952,12,31)]))
    
    @property
    @timing
    def sub_ocg_dataset(self):
        sub = multipolygon_operation(self.nc_path,
                                     self.nc_var_name,
                                     ocg_opts=self.nc_opts,
                                     polygons=[
                                               {'gid':99,'geom':self.nebraska()},
#                                               {'gid':100,'geom':self.iowa()},
#                                               {'gid':200,'geom':self.vermont()}
                                               ],
                                     time_range=[datetime.datetime(2011,1,1),
                                                 datetime.datetime(2013,12,31)],
                                     level_range=None,
                                     clip=False,
                                     union=False,
                                     in_parallel=True,
                                     max_proc=8,
                                     max_proc_per_poly=2)
        return(sub)
            
            
class TestStats(TestData,unittest.TestCase):
    
    @staticmethod
    def change_from_mean(values,mean=2.0):
        return(np.mean(values) - mean)
    
    @staticmethod
    def threshold_values(values,threshold=2.0):
        days = filter(lambda x: x > threshold, values)
        return(len(days))
    
    @timing
    def test_summary(self):
        to_disk = False
        use_stat = True
        procs = 4
        sub = self.sub_ocg_dataset
        db = sub.to_db(to_disk=to_disk,procs=procs)
            
        if use_stat:
            st = OcgStat(db,sub,('year',),procs=procs)
            funcs = [
                     {'function':np.mean},
                     {'function':np.std},
                     {'function':self.change_from_mean,'name':'meanchg','args':[2.0,]},
                     {'function':self.threshold_values,'name':'threshval','kwds':{'threshold':2.0}}
                     ]
            st.calculate_load(funcs)
        conv = [
#                    CsvConverter(db,'foo',use_stat=use_stat),
#                    GeojsonConverter(db,'foo',use_stat=use_stat),
#                    ShpConverter(db,'foo',use_stat=use_stat),
#                    LinkedCsvConverter(db,'foo',use_stat=use_stat),
                LinkedShpConverter(db,'foo',use_stat=use_stat),
#                    SqliteConverter(db,'foo')
                ]

        for c in conv:
            print(c)
#                payload = c.convert()
#            print(payload[0][2]['buffer'].getvalue())
            print(c.write())


class TestNcConversion(TestData,unittest.TestCase):
    
    def test_convert(self):
        ocg_dataset = self.ocg_dataset
        sub = self.sub_ocg_dataset
        db = sub.as_sqlite()
#        grid = sub.to_grid_dict(ocg_dataset)
#        for key,val in grid.iteritems(): print key,val.shape
        conv = NcConverter(db,'foo')
        path = conv.write(sub,ocg_dataset)
        dd = nc.Dataset(path,'r')
        value = dd.variables['value']
#        conv.convert(sub,ocg_dataset)
#        import ipdb;ipdb.set_trace()
            
#            print('')
#            if type(payload) not in [list,tuple]:
#                print(payload)
#            else:
#                try:
#                    for ii in payload:
#                        print ii['buffer'].getvalue()
#                except TypeError:
#                    for ii in payload[0]:
#                        print ii['buffer'].getvalue()
#                    print(payload[1])
#        import ipdb;ipdb.set_trace()

class TestSubOcgStat(TestData,unittest.TestCase):
    
    _ss = None
    
    @property
    def ss(self):
        if self._ss is None:
            self._ss = SubOcgStat(self.sub_ocg_dataset,['year'],procs=8)
        return(self._ss)
    
    @staticmethod
    def change_from_mean(values,mean=2.0):
        return(np.mean(values) - mean)
    
    @staticmethod
    def threshold_values(values,threshold=2.0):
        days = filter(lambda x: x > threshold, values)
        return(len(days))
    
    def test_get_distinct_groups(self):
        self.ss.get_distinct_groups()
        
    def test_calculate(self):
        funcs = [
                {'function':np.mean,'name':'mean'},
                {'function':np.std,'name':'std'},
                {'function':self.change_from_mean,'name':'meanchg','args':[2.0,]},
                {'function':self.threshold_values,'name':'threshval','kwds':{'threshold':2.0}}
                ]
        self.ss.calculate(funcs)
    
    def test_url(self):
        from django.test.client import Client
        
#        url = ('/api/archive/usgs-cida-maurer/model/miroc3.2%28medres%29/scenario'
#               '/sres-a1b/run/2/temporal/2000-01-01+2000-03-01/spatial'
#               '/intersects+polygon%28%28-104+39,+-95+39,+-95+44,+-104+39%29%29'
#               '/aggregate/false/variable/pr.nc?stat=min+gt(5):gt5'
#               '+between(5,10):btwn5_10&grouping=year')
        url = ('/api/archive/usgs-cida-maurer/model/miroc3.2%28medres%29/scenario'
          '/sres-a1b/run/2/temporal/2000-01-01+2029-12-31/spatial'
          '/intersects+states'
          '/aggregate/false/variable/tas.nc?stat=gt(38):gt_100f&grouping=year')
        
        c = Client()
        t1 = time.time()
        response = c.get(url)
        print((time.time() - t1)/60)
        assert(response.status_code == 200)

if __name__ == "__main__":
    import sys;sys.argv = ['', 'TestSubOcgStat.test_url']
    unittest.main()