
"Util contains functions and classes which are required by pymel.  These helper utilities do not require pymel to operate and can be useful in other code."

import sys, codecs, os, os.path, re, platform
from exceptions import *
from collections import *

from namedtuple import namedtuple
from argutils import *
import envparse

if os.name == 'nt' :
    maya = 'maya.exe'
    sep = ';'
else :
    maya = 'maya.bin'
    sep = ':'
    
#from maya.cmds import encodeString

class Singleton(object) :
    """
Singleton classes can be derived from this class
You can derive from other classes as long as Singleton comes first (and class doesn't override __new__

    >>> class uniqueImmutableDict(Singleton, dict) :
    >>>     def __init__(self, value) :
    >>>        # will only be initialied once
    >>>        if not len(self):
    >>>            super(uniqueDict, self).update(value)
    >>>        else :
    >>>            raise TypeError, "'"+self.__class__.__name__+"' object does not support redefinition"
    >>>   # You'll want to override or get rid of dict herited set item methods
    """
    def __new__(cls, *p, **k):
        if not '_the_instance' in cls.__dict__:
            cls._the_instance = super(Singleton, cls).__new__(cls)
        return cls._the_instance

try:
    from collections import defaultdict
except:
    class defaultdict(dict):
        def __init__(self, default_factory=None, *a, **kw):
            if (default_factory is not None and
                not hasattr(default_factory, '__call__')):
                raise TypeError('first argument must be callable')
            dict.__init__(self, *a, **kw)
            self.default_factory = default_factory
        def __getitem__(self, key):
            try:
                return dict.__getitem__(self, key)
            except KeyError:
                return self.__missing__(key)
        def __missing__(self, key):
            if self.default_factory is None:
                raise KeyError(key)
            self[key] = value = self.default_factory()
            return value
        def __reduce__(self):
            if self.default_factory is None:
                args = tuple()
            else:
                args = self.default_factory,
            return type(self), args, None, None, self.iteritems()
        def copy(self):
            return self.__copy__()
        def __copy__(self):
            return type(self)(self.default_factory, self)
        def __deepcopy__(self, memo):
            import copy
            return type(self)(self.default_factory,
                              copy.deepcopy(self.items()))

        def __repr__(self):
            return 'defaultdict(%s, %s)' % (self.default_factory,
                                            dict.__repr__(self))

class metaStatic(type) :
    """Static singleton dictionnary metaclass to quickly build classes
    holding predefined immutable dicts"""
    def __new__(mcl, classname, bases, classdict):
        # Class is a Singleton and some base class (dict or list for instance), Singleton must come first so that it's __new__
        # method takes precedence
        base = bases[0]
        if Singleton not in bases :
            bases = (Singleton,)+bases        
        # Some predefined methods
        def __init__(self, value=None):
            # Can only create once)       
            if value is not None :
                # Can only init once
                if not self:
                    # Use the ancestor class dict method to init self
                    # base.update(self, value)
                    # self = base(value)
                    base.__init__(self, value)
                else :
                    raise TypeError, "'"+classname+"' object does not support redefinition"
        # delete the setItem methods of dict we don't want (read only dictionary)
        def __getattribute__(self, name):         
            remove = ('clear', 'update', 'pop', 'popitem')
            if name in remove :
                raise AttributeError, "'"+classname+"' object has no attribute '"+name+"'" 
#            elif self.__dict__.has_key(name) :
#                return self.__dict__[name]
            else :
                return base.__getattribute__(self, name)
        # Cnnot set an item of the read only dict or list
        def __setitem__(self,key,val) :
            raise TypeError, "'"+classname+"' object does not support item assignation"           
        # Now add methods of the defined class, as long as it doesn't try to redefine
        # __new__, __init__, __getattribute__ or __setitem__
        newdict = { '__slots__':[], '__dflts__':{}, '__init__':__init__, '__getattribute__':__getattribute__, '__setitem__':__setitem__ }
        # Note: could have defined the __new__ method like it is done in Singleton but it's as easy to derive from it
        for k in classdict :
            if k.startswith('__') and k.endswith('__') :
                # special methods, copy to newdict unless they conflict with pre-defined methods
                if k in newdict :
                    warnings.warn("Attribute %r is predefined in class %r of type %r and can't be overriden" % (k, classname, mcl.__name__))
                else :
                    newdict[k] = classdict[k]
            else :
                # class variables
                newdict['__slots__'].append(k)
                newdict['__dflts__'][k] = classdict[k]
        return super(metaStatic, mcl).__new__(mcl, classname, bases, newdict)

           

class ModuleInterceptor(object):
    """
    This class is used to intercept an unset attribute of a module to perfrom a callback. The
    callback will only be performed if the attribute does not exist on the module. Any error raised
    in the callback will cause the original AttributeError to be raised.
        
        >>> def cb( module, attr):
        >>>     if attr == 'this':
        >>>         print "intercepted"
        >>>     else:
        >>>         raise ValueError        
        >>> sys.modules[__name__] = ModuleInterceptor(__name__, cb)
    
    The class does not work when imported into the main namespace.    
    """
    def __init__(self, moduleName, callback):
        self.module = __import__( moduleName , globals(), locals(), [''] )
        self.callback = callback
    def __getattr__(self, attr):
        try:
            return getattr(self.module, attr)
        except AttributeError, msg:
            try:
                self.callback( self.module, attr)
            except:
                raise AttributeError, msg
#-----------------------------------------------
#  Pymel Internals
#-----------------------------------------------
def pythonToMel(arg):
    if isinstance(arg,basestring):
        return '"%s"' % cmds.encodeString(arg)
    elif isIterable(arg):
        return '{%s}' % ','.join( map( pythonToMel, arg) ) 
    return unicode(arg)
            
def capitalize(s):
    return s[0].upper() + s[1:]

def uncapitalize(s):
    return s[0].lower() + s[1:]
                        
  

def cacheProperty(getter, attr_name, fdel=None, doc=None):
    """a property type for getattr functions that only need to be called once per instance.
        future calls to getattr for this property will return the previous non-null value.
        attr_name is the name of an attribute in which to store the cached values"""
    def fget(obj):
        val = None
    
        if hasattr(obj,attr_name):            
            val = getattr(obj, attr_name)
            #print "cacheProperty: retrieving cache: %s.%s = %s" % (obj, attr_name, val)
            
        if val is None:
            #print "cacheProperty: running getter: %s.%s" %  (obj, attr_name)
            val = getter(obj)
            #print "cacheProperty: caching: %s.%s = %s" % (obj, attr_name, val)
            setattr(obj, attr_name, val )
        return val
                
    def fset(obj, val):
        #print "cacheProperty: setting attr %s.%s=%s" % (obj, attr_name, val)
        setattr(obj, attr_name, val)

    return property( fget, fset, fdel, doc)

def moduleDir():
    return os.path.dirname( os.path.dirname( sys.modules[__name__].__file__ ) )
    #return os.path.split( sys.modules[__name__].__file__ )[0]

# A source commande that will search for the Python script "file" in the specified path
# (using the system path if none is provided) path and tries to call execfile() on it
def source (file, searchPath=None, recurse=False) :
    """Looks for a python script in the specified path (uses system path if no path is specified)
        and executes it if it's found """
    filepath = os.path(file)
    filename = filepath.basename()
    if searchPath is None :
        searchPath=sys.path
    if not util.isIterable(searchPath) :
        searchPath = list((searchPath,))
    itpath = iter(searchPath)
    #print "looking for file as: "+filepath
    while not filepath.exists() :
        try :
            p = os.path(itpath.next()).realpath().abspath()
            filepath = filepath.joinpath(p, filename)
            #print 'looking for file as: '+filepath
            if recurse and not filepath.exists() :
                itsub = os.walk(p)
                while not filepath.exists() :
                    try :
                        root, dirs, files = itsub.next()
                        itdirs = iter(dirs)
                        while not filepath.exists() :
                            try :
                                filepath = filepath.joinpath(Path(root), os.path(itdirs.next()), filename)
                                #print 'looking for file as: '+filepath
                            except :
                                pass
                    except :
                        pass
        except :
            raise ValueError, "File '"+filename+"' not found in path"
            # In case the raise exception is replaced by a warning don't forget to return here
            return
    # print "Executing: "+filepath
    return execfile(filepath)


def getMayaLocation():
    try:
        return os.environ['MAYA_LOCATION']
    except:
        return os.path.dirname( os.path.dirname( sys.executable ) )
        
def getMayaVersion(extension=True):
    """ Returns the maya version (ie 2008), with extension (known one : x64 for 64 bit cuts) if extension=True """
    
    try :
        from maya.cmds import about
        versionStr = about(version=True)
    except :
        versionStr = getMayaLocation()
    
    # problem with service packs nottion, must be able to match things such as :
    # '2008 Service Pack 1 x64', '2008x64', '2008', '8.5'
    ma = re.search( "((?:maya)?(?P<base>[\d.]+)(?:(?:[ ].*[ ])|(?:-))?(?P<ext>x[\d.]+)?)", versionStr)
    version = ma.group('base')
    if extension and (ma.group('ext') is not None) :
        version += "-"+ma.group('ext')
    return version
                        
# parse the Maya.env file and set the environement variablas and python path accordingly
def parseMayaenv(envLocation=None, version=None) :
    """ parse the Maya.env file and set the environement variablas and python path accordingly.
        You can specify a location for the Maya.env file or the Maya version"""
    name = 'Maya.env'

        
    envPath = None
    if envLocation :
        envPath = envLocation
        if not os.path.isfile(envPath) :
            envPath = os.path.join(envPath, name)
            
    # no Maya.env specified, we look for it in MAYA_APP_DIR
    if not envPath or not envPath.isfile() :
        if not os.environ.has_key('MAYA_APP_DIR') :
            home = os.environ.get('HOME', None)
            if not home :
                warnings.warn("Neither HOME nor MAYA_APP_DIR is set, unable to find location of Maya.env", ExecutionWarning)
                return False
            else :
                maya_app_dir = os.path.join(home, 'maya')
        else :
            maya_app_dir = os.environ['MAYA_APP_DIR']
        # try to find which version of Maya should be initialized
        if not version :
            # try to query version, will only work if reparsing env from a working Maya
            version = getMayaVersion(extension=True)
            if version is None:
                # if run from Maya provided mayapy / python interpreter, can guess version
                print "Unable to determine which verson of Maya should be initialized, trying for Maya.env in %s" % maya_app_dir
        # look first for Maya.env in 'version' subdir of MAYA_APP_DIR, then directly in MAYA_APP_DIR
        if version and os.path.isfile(os.path.join(maya_app_dir, version, name)) :
            envPath = os.path.join(maya_app_dir, version, name)
        else :
            envPath = os.path.join(maya_app_dir, name)

    # finally if we have a possible Maya.env, parse it
    if os.path.isfile(envPath) :
        try :
            envFile = open(envPath)
        except :
            warnings.warn ("Unable to open Maya.env file %s" % envPath, ExecutionWarning)
            return False
        success = False
        try :
            envTxt = envFile.read()
            envVars = envparse.parse(envTxt)
            # update env vars
            for v in envVars :
                #print "%s was set or modified" % v
                os.environ[v] = envVars[v]
            # add to syspath
            if envVars.has_key('PYTHONPATH') :
                #print "sys.path will be updated"
                plist = os.environ['PYTHONPATH'].split(sep)
                for p in plist :
                    if not p in sys.path :
                        sys.path.append(p)
            success = True
        finally :
            envFile.close()
            return success
    else :
        if version :
            print"Found no suitable Maya.env file for Maya version %s" % version
        else :
            print"Found no suitable Maya.env file"
        return False

def _addEnv( env, value ):
    if os.name == 'nt' :
        sep = ';'
    else :
        sep = ':'
    if env not in os.environ:
        os.environ[env] = value
    else:
        os.environ[env] = sep.join( os.environ[env].split(sep) + [value] )
                    
# Will test initialize maya standalone if necessary (like if scripts are run from an exernal interpeter)
# returns True if Maya is available, False either
def mayaInit(forversion=None) :
    """ Try to init Maya standalone module, use when running pymel from an external Python inerpreter,
    it is possible to pass the desired Maya version number to define which Maya to initialize """

    # test that Maya actually is loaded and that commands have been initialized,for the requested version        
    try :
        from maya.cmds import about        
        version = eval("about(version=True)");
    except :
        version = None

    if forversion :
        if version == forversion :
            return True
        else :
            print "Maya is already initialized as version %s, initializing it for a different version %s" % (version, forversion)
    elif version :
            return True
                
    # reload env vars, define MAYA_ENV_VERSION in the Maya.env to avoid unneeded reloads
    envVersion = os.environ.get('MAYA_ENV_VERSION', None)
    
    if (forversion and envVersion!=forversion) or not envVersion :
        if not parseMayaenv(version=forversion) :
            print "Could not read or parse Maya.env file"
    
    # add necessary environment variables and paths for importing maya.cmds, a la mayapy
    # currently just for osx
    if platform.system() == 'Darwin' :
        frameworks = os.path.join( os.environ['MAYA_LOCATION'], 'Frameworks' )    
        _addEnv( 'DYLD_FRAMEWORK_PATH', frameworks )
        
        # this *must* be set prior to launching python
        #_addEnv( 'DYLD_LIBRARY_PATH', os.path.join( os.environ['MAYA_LOCATION'], 'MacOS' ) )
        # in lieu of setting PYTHONHOME like mayapy which must be set before the interpretter is launched, we can add the maya site-packages to sys.path
        try:
            pydir = os.path.join(frameworks, 'Python.framework/Versions/Current')
            mayapyver = os.path.split( os.path.realpath(pydir) )[-1]
            #print os.path.join( pydir, 'lib/python%s/site-packages' % mayapyver )
            sys.path.append(  os.path.join( pydir, 'lib/python%s/site-packages' % mayapyver ) )
        except:
            pass    
        
    if not sys.modules.has_key('maya.standalone') or version != forversion:
        try :
            import maya.standalone #@UnresolvedImport
            maya.standalone.initialize(name="python")
        except :
            pass

    try :
        from maya.cmds import about    
        reload(maya.cmds) #@UnresolvedImport
        version = eval("about(version=True)")
        return (forversion and version==forversion) or version
    except :
        return False

# Fix for non US encodings in Maya
def encodeFix():
    if mayaInit() :
        from maya.cmds import about
        
        mayaEncode = about(cs=True)
        pyEncode = sys.getdefaultencoding()     # Encoding tel que defini par sitecustomize
        if mayaEncode != pyEncode :             # s'il faut redefinir l'encoding
            #reload (sys)                       # attention reset aussi sys.stdout et sys.stderr
            #sys.setdefaultencoding(newEncode) 
            #del sys.setdefaultencoding
            #print "# Encoding changed from '"+pyEncode+'" to "'+newEncode+"' #"
            if not about(b=True) :              # si pas en batch, donc en mode UI, redefinir stdout et stderr avec encoding Maya
                import maya.utils    
                try :
                    import maya.app.baseUI
                    # Replace sys.stdin with a GUI version that will request input from the user
                    sys.stdin = codecs.getreader(mayaEncode)(maya.app.baseUI.StandardInput())
                    # Replace sys.stdout and sys.stderr with versions that can output to Maya's GUI
                    sys.stdout = codecs.getwriter(mayaEncode)(maya.utils.Output())
                    sys.stderr = codecs.getwriter(mayaEncode)(maya.utils.Output( error=1 ))
                except ImportError :
                    print "Unable to import maya.app.baseUI"    

def timer( command='pass', number=10, setup='import pymel' ):
    import timeit
    t = timeit.Timer(command, setup)
    time = t.timeit(number=number)
    print "command took %.2f sec to execute" % time
    return time
    
def toZip( directory, zipFile ):
    """Sample for storing directory to a ZipFile"""
    import zipfile

    zipFile = path(zipFile)
    if zipFile.exists(): zipFile.remove()
    
    z = zipfile.ZipFile(
        zipFile, 'w', compression=zipfile.ZIP_DEFLATED
    )
    if not directory.endswith(os.sep):
        directory += os.sep
        
    directory = path(directory)
    
    for subdir in directory.dirs('[a-z]*') + [directory]: 
        print "adding ", subdir
        for fname in subdir.files('[a-z]*'):
            archiveName = fname.replace( directory, '' )            
            z.write( fname, archiveName, zipfile.ZIP_DEFLATED )
    z.close()
    return zipFile

def release( username=None, password = None):
    
    # check that everything is importing ok
    import ply.lex as lex
    import pymel.examples.example1
    import pymel.examples.example2
    from pymel.types.path import path
        
    baseDir = moduleDir()
    tmpDir = baseDir.parent / "release" / str(pymel.__version__)
    if not tmpDir.exists():
        tmpDir.makedirs()
        
    releaseDir = tmpDir / "pymel"
    if releaseDir.exists():
        releaseDir.rmtree()
    print "copying to release directory", tmpDir
    baseDir.copytree( tmpDir / "pymel" )
    baseDir = tmpDir
    
    print "cleaning up"

    svndirs = [d for d in baseDir.walkdirs( '.*' )]
    for d in svndirs:
        print "removing", d
        d.rmtree()    
    for f in baseDir.walkfiles( '*.pyc' ):
        print "removing", f
        f.remove()
    for f in baseDir.walkfiles( '._*' ):
        print "removing", f    
        f.remove()    
        
    print "done"
    
    return

    #zipFile = baseDir.parent / 'pymel-%s.zip' % str(pymel.__version__)
    zipFile = baseDir.parent / 'pymel.zip'
    print "zipping up %s into %s" % (baseDir, zipFile)
    toZip(     baseDir, zipFile )

    import googlecode    
    if username and password:
        print "uploading to googlecode"
        googlecode.upload(zipFile, 'pymel', username, password, 'pymel ' + str(pymel.__version__), 'Featured')
        print "done"