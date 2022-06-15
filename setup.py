from setuptools import setup
from setuptools import find_packages

for package in find_packages():
    print(package)
setup(
    name='intellimation_tcf',
    version='0.1',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    url='https://github.com/schandrika/intellimation_tcf',
    license='',
    author='volttron',
    author_email='chandrika@pnnl.gov',
    description='Parsers to generate VOLTTRON agent configurations '
                'based on haystack tags',
    entry_points={
        'console_scripts': [
            'config-gen-db.driver=volttron.haystack.parser.driver.'
            'intellimation.config_intellimation:main',
            'config-gen-json.driver=volttron.haystack.parser.driver.'
            'config_from_json:main',
            'config-gen-db.airsidercx=volttron.haystack.parser.airsidercx.'
            'intellimation.config_intellimation:main',
            'config-gen-json.airsidercx=volttron.haystack.parser.airsidercx.'
            'config_from_json:main',
        ]
    }
)