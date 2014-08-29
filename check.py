#!/usr/bin/env python

from Cheetah.Template import Template
import os.path
import humanfriendly
import subprocess
import yaml
import sys

# The hierarchy of objects is:
# backup ----< validators ----< tests
# each backup can have multiple validators, which regroup
# tests working on the same level. Eg, a file validator will
# test characteristichs of the file, but not its content.
# a mysql validator could possibly work on the content.

################################################################################
# The test classes are used to perform one test on 
# the backup. 
# Each instance is initialised with its key and value
# from the yaml config file.
# The key is kept only for possible logging.
# The value holds the data against which to validate 
# the backup
# The test are done in the check method, which takes
# the backup to test as argument.
class Test:
  def __init__(self, params={}):
    self.params = params
    # set default messages
    self.success_message = "Test did pass. "+self.__class__.__name__
    self.error_message =   "Test did NOT pass. "+self.__class__.__name__
    self.prepare()
  def prepare(self):
    # Used in derived classes to setup the instance more
  # precisely
    pass
  def check(self,b):
    self.run_test(b)
    if self.result:
      print(self.success_message)
      message=self.success_message
    else:
      print(self.error_message)
      message=self.error_message
    b.log_message(self.result, message)
    return self.result

# Check size of backup is above the minimum value as
# specified in the yaml.
# minsize can be specified in bytes or with the unit suffix
# eg : 5Kb
class MinsizeTest(Test):
  def prepare(self):
    # parse file sizes with humanfriendly
    if self.params.__class__.__name__=="str":
      self.minsize=humanfriendly.parse_size(self.params)
    else:
      self.minsize=self.params


  def run_test(self,b):
    # setup messages
    self.success_message = "Minimum size respected ( "+ str(b.specs.get("size")) +" !< " + str(self.minsize) +" )."
    self.error_message = "Minimum size not respected ( "+ str(b.specs.get("size")) +" < " + str(self.minsize) +" )."

    # perform test
    self.result = b.specs.get("size")>=self.minsize

class FiletypeTest(Test):
  def run_test(self,b):
    # set messages
    self.success_message = "File type correct ( "+ b.specs.get("mimetype") +" == " + self.params +" )."
    self.error_message =   "File type INCORRECT ( "+ b.specs.get("mimetype") +" != " + self.params +" )."
    # set result
    self.result = b.specs.get("mimetype") == self.params


class CountTest(Test):
  def run_test(self,b):
    # set messages
    self.success_message = "Number of matches correct ( "+ str(b.specs.get("count")) +" == " + str(self.params) +" )."
    self.error_message =   "Number of matches INCORRECT ( "+ str(b.specs.get("count")) +" != " + str(self.params) +" )."
    # set result
    self.result = b.specs.get("count") == self.params

class MinFileCountTest(Test):
  def run_test(self,b):
    # set messages
    self.success_message = "Number of file correct ( "+ str(b.specs.get("files_count")) +" >= " + str(self.params) +" )."
    self.error_message =   "Number of file INCORRECT ( "+ str(b.specs.get("files_count")) +" <= " + str(self.params) +" )."
    # set result
    self.result = b.specs.get("files_count") >= self.params


class BackupSpecs:
  def __init__(self):
    self.specs={}
  def set(self,k,v):
    self.specs[k]=v
  def get(self,k):
    return self.specs[k]


################################################################################
# Backups hold specs about the storage of the backup to be validated,
# and other data like name and description.
# It initialises the validators defined for it in the yaml file
class Backup:
  def __init__(self, yml):
    # path is value configure in yaml file
    # location is value as discovered by backup checker. At start, same value
    self.location = yml['location']
    self.path = self.location
    self.name     = yml["name"]
    self.kind     = yml["kind"]
    self.specs    = BackupSpecs()
    if yml["tests"]: # and  yml["validators"]
      self.tests = [self.initialize_test(k,v) for k,v in yml["tests"].iteritems()]
    else:
      self.tests = []
    self.messages = []
    # collect specs only if backup exists
    if self.exists():
      self.status = 'unchecked'
      self.collect_specs()
    else:
      self.set_invalid()
  def exists(self):
    return os.path.isfile(self.location)
  def collect_specs(self):
    pass
  def initialize_test(self,k,v):
    name = k.title().replace("_","")+"Test"
    klass = globals()[name]
    return klass(v)
  def set_valid(self):
    self.status='valid'
  def set_invalid(self):
    self.status='invalid'
  def done(self):
    self.status!="unchecked"
  def is_invalid(self):
    return self.status=='invalid'
  def log_message(self,success, message):
    self.messages.append( (success, message) )


  def __str__(self):
    s= "Backup " + self.name + "( " + self.location + ") : " + self.status +"\n"
    for success,m in self.messages:
      s+=m+"\n"
    return s

class FileBackup(Backup):
  def collect_specs(self):
    self.specs.set("size",os.path.getsize(self.location))

    output=subprocess.check_output("file --mime-type "+self.location, shell=True)
    path,mimetype = map(str.rstrip,map(str.lstrip,output.split(":")))
    self.specs.set("mimetype",mimetype)

import glob
class FileglobBackup(FileBackup):
  def exists(self):
    found = glob.glob(self.location)
    count = len(found)
    if count<1:
      return False
    else:
      self.matches =  found
      self.count = count
      return True
  def collect_specs(self):
    self.specs.set("count", self.count)
    total_size = sum(os.path.getsize(l) for l in self.matches)
    self.specs.set("size",total_size)
    self.specs.set("matches",self.matches)

    if self.specs.get("count")==1:
      output=subprocess.check_output("file --mime-type "+self.location, shell=True)
      path,mimetype = map(str.rstrip,map(str.lstrip,output.split(":")))
      self.specs.set("mimetype",mimetype)
    else:
      # do not set mimetype if multiple matches
      self.specs.set("mimetype",None)

import boto
class S3FileBackup(Backup):
  def __init__(self,yml):
    # needed to break cyclic dependency
    # move all specific behaciour to collect_specs to avoid this?
    self.location = yml["location"]
    self.init_s3_connection(yml)
    self.init_s3_object()
    Backup.__init__(self,yml)
  def init_s3_connection(self,yml):
    s3_auth = yaml.load(open(yml["s3_auth"]).read().__str__())
    self.conn = boto.connect_s3(
        aws_access_key_id= s3_auth["access_key"],
        aws_secret_access_key = s3_auth["secret_key"])
  def init_s3_object(self):
    bucket_name,object_name=self.location.split('/')
    bucket=self.conn.get_bucket(bucket_name)
    self.s3_object=bucket.get_key(object_name)
  def exists(self):
    return self.s3_object != None and self.s3_object.exists()
  def collect_specs(self):
    self.specs.set("size",self.s3_object.size)
    self.specs.set("mimetype",self.s3_object.content_type)
    #k.size
    #k.last_modified
    #import time
    #time.strptime(k.last_modified, '%a, %d %b %Y %H:%M:%S %Z')
    #k.name
    #k.content_type

import fnmatch
class S3FileglobBackup(S3FileBackup):
  def init_s3_object(self):
    bucket_name,object_name=self.location.split('/')
    bucket=self.conn.get_bucket(bucket_name)

    objects = bucket.list()

    count = 0
    matches = []
    for key in objects:
      if fnmatch.fnmatch(key.name,object_name):
        count = count + 1
        matches.append(key)
    if count>0:
      self.count=count
      self.s3_objects=matches
      return True
    else:
      self.s3_object = None
      return False                   

  def collect_specs(self):
    self.specs.set("count",self.count)

    total_size = sum(o.size for o in self.s3_objects)
    self.specs.set("size",total_size)

    if self.specs.get("count")==1:
      self.specs.set("mimetype",self.s3_objects[0].content_type)
    else:
      # do not set mimetype if multiple matches
      self.specs.set("mimetype",None)

  def exists(self):
    return self.count>0

import paramiko
class SshFileBackup(Backup):
  def __init__(self,yml):
    self.location = yml["location"]
    self.init_sftp_connection()
    Backup.__init__(self,yml)

  def init_sftp_connection(self):
    self.ssh = paramiko.SSHClient()
    # FIXME
    self.ssh.set_missing_host_key_policy( paramiko.AutoAddPolicy())
    self.host,self.remote_path=self.location.split(":")
    self.ssh.connect(self.host)
    self.sftp=self.ssh.open_sftp()

    
  def exists(self):
    #FIXME
    return True

  def collect_specs(self):
    stats = self.sftp.lstat(self.remote_path)
    self.specs.set("size",stats.st_size)
    self.specs.set("mtime", stats.st_mtime)

class SshDirBackup(Backup):
  def __init__(self,yml):
    self.location = yml["location"]
    self.init_sftp_connection()
    Backup.__init__(self,yml)

  def init_sftp_connection(self):
    self.ssh = paramiko.SSHClient()
    # FIXME
    self.ssh.set_missing_host_key_policy( paramiko.AutoAddPolicy())
    self.host,self.remote_path=self.location.split(":")
    self.ssh.connect(self.host)
    self.sftp=self.ssh.open_sftp()

    
  def exists(self):
    #FIXME
    return True

  def collect_specs(self):
    stdin,stdout,stderr=self.ssh.exec_command("du -sb "+self.remote_path)
    self.specs.set("size", int(stdout.readlines()[0].split('\t')[0]) )
    stats = self.sftp.lstat(self.remote_path)
    self.specs.set("mtime", stats.st_mtime)
    stdin,stdout,stderr=self.ssh.exec_command("ls "+ self.remote_path + "| wc -l")
    self.specs.set("files_count", int(stdout.readlines()[0])) 

# Maybe (?) add handle to the file in the backup instance?
# that would be handle to local file or to the s3 key of the backup file

class BackupChecker:
  def __init__(self,config_file):
    # Read config and initialise backup instances
    self.config = yaml.load(Template(file=config_file).__str__())
    print(self.config)
    self.backups= [self.init_backup(b) for b in self.config['backups']]
  def init_backup(self,yml):
    name = yml["kind"].title().replace("_","")+"Backup"
    klass = globals()[name]
    return klass(yml)

  def check_backup(self,b):
    # Check one backup

    # INIT
    # i is index, l length of validators list
    i=0
    l=len(b.tests)
    
    # INV : 
    #  0<=i<l
    #  for 0<=j<i,   b.validators[j] was tested
    while i<l and not b.is_invalid():
      t=b.tests[i]
      # if the check fails; we set the backup as invalid
      # and loop will stop
      if not t.check(b):
        b.set_invalid()
      i=i+1
    # if we went through the whole list without invalidating it, the 
    # backup can be validated
    if i==l and not b.is_invalid():
      b.set_valid()

    
  def check(self):
    for i,backup in enumerate(self.backups):
      self.check_backup(backup)

  def __str__(self):
    s = "BackupChecker results\n"
    s+= "---------------------\n"
    for b in self.backups:
      s+=str(b)
      s+="\n"
    return s
  def to_html(self):
      return Template(file="report.html", searchList=[{"bc":self}]).__str__()

bc=BackupChecker(sys.argv[1])
bc.check()
print(bc)
print(bc.to_html())
