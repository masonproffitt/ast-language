import setuptools

setuptools.setup(name='ast_language',
                 version=0.1,
                 packages=setuptools.find_packages(exclude=['tests']),
                 install_requires=['lark-parser>=0.6.5'],
                 package_data={'ast_language': ['syntax.lark']},
                 author='Mason Proffitt',
                 author_email='masonlp@uw.edu',
                 url='https://github.com/iris-hep/ast-language')
