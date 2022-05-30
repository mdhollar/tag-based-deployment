This repository contains code for generating VOLTTRON agent configuration based on Haystack tags. Currently there is config generator for 

1. Platform Driver Agent 
2. AirsideRCx Agent

# Currently supported device types:

1. AHU
2. VAV

# Currently supported datasources for haystack tags

1. Postgres database that contains haystack tags for equipments, and points.  
2. Json format files - one for equipement tags and one for point tags

# Platform Driver configuration generator classes:

1. DriverConfigGenerator: Base class that parses the configuration
2. IntellimationDriverConfigGenerator: Derives from DriverConfigGenerator and reads haystack tags from Intellimation postgres database and generates platform driver 
   configurations for AHUs and VAVs. 
4. JsonDriverConfigGenerator: Derives from DriverConfigGenerator and reads haystack tags from two json files - one for equipment tags and one for point tags - and 
   generates driver configurations for AHUs and VAVs
   
# AirsideRCx configuration generator classes:

1. DriverConfigGenerator: Base class that parses the configuration
2. IntellimationDriverConfigGenerator: Derives from DriverConfigGenerator and reads haystack tags from Intellimation postgres database and generates platform driver 
   configurations for AHUs and VAVs. 
4. JsonDriverConfigGenerator: Derives from DriverConfigGenerator and reads haystack tags from two json files - one for equipment tags and one for point tags - and 
   generates driver configurations for AHUs and VAVs
