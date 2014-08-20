#!/usr/bin/env python

from Cheetah.Template import Template
import os.path
import humanfriendly
import subprocess
import yaml

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
  def __init__(self, k , v):
    self.key = k
    self.value = v
    # set default messages
    self.success_message = "Test of "+ self.key + " " + self.value+" dit pass."
    self.error_message =   "Test of "+ self.key + " " + self.value+" dit NOT pass"
    self.prepare()
  def prepare(self):
  # Used in derived classes to setup the instance more
  # precisely
    pass
  def check(self,b):
    self.run_test(b)
    if self.result:
      message=self.success_message
    else:
      message=self.error_message
    b.log_message(self.result, message)
    return self.result

# Preliminary tests for a local file backup.
class FileTest(Test):
  def run_test(self,b):
    self.success_message = "File "+b.location+" exists!"
    self.error_message =   "File "+b.location+" not found!"
    self.result =  os.path.isfile(b.location)

# Check size of backup is above the minimum value as
# specified in the yaml.
# minsize can be specified in bytes or with the unit suffix
# eg : 5Kb
class FileMinsizeTest(Test):
  def prepare(self):
    # parse file sizes with humanfriendly
    if self.value.__class__.__name__=="str":
      self.minsize=humanfriendly.parse_size(self.value)
    else:
      self.minsize=self.value

    
  def run_test(self,b):
    self.size=os.path.getsize(b.location)
    # setup messages
    self.success_message = "Minimum size respected ( "+ str(self.size) +" !< " + str(self.minsize) +" )."
    self.error_message = "Minimum size not respected ( "+ str(self.size) +" < " + str(self.minsize) +" )."
    
    # perform test
    self.result = self.size>=self.minsize

class FileFiletypeTest(Test):
  def run_test(self,b):
    # get result
    output=subprocess.check_output("file --mime-type "+b.location, shell=True)
    path,filetype = map(str.rstrip,map(str.lstrip,output.split(":")))
    # set messages
    self.success_message = "File type correct ( "+ filetype +" == " + self.value +" )."
    self.error_message =   "File type INCORRECT ( "+ filetype +" != " + self.value +" )."
    # set result
    self.result = filetype == self.value


import glob
class FileglobTest(Test):
  def run_test(self,b):
    found = glob.glob(b.location)
    l = len(found)
    if l==0:
      self.error_message =   "File matching"+b.location+" not found!"
      self.result=False
    elif l>1:
      self.error_message =   "Multiple files matching"+b.location+" found!"
      self.result=False
    else:
      self.success_message =   "File matching"+b.location+" found!"
      self.result=True
      # set file location in backup
      b.location=found[0]

FileglobMinsizeTest = FileMinsizeTest
FileglobFiletypeTest= FileFiletypeTest


################################################################################
# A validator groups tests.
# 
class Validator:
  def __init__(self,yml):
    self.kind=yml['kind']
    # remove kind from dictionary so we can use all other keys as tests
    # kind is used to run preliminary tests of the validator. Eg for a file
    # validator, the presence of the file is first checked.
    del yml["kind"]
    self.yml=yml
    self.tests = [self.initialize_test(k,v) for k,v in self.yml.iteritems()]

  def initialize_test(self,k,v):
    # initialize instance of correct test class
    name = self.kind.title()+k.title().replace("_","") + "Test"
    klass = globals()[name]
    return klass(k,v)

  def check(self,b):
    # First run basic validation for this kinf od validation
    # if successful, try all other tests.
    name = self.kind.title().replace("_","") + "Test"
    klass = globals()[name]
    basic_test = klass("kind","file")
    if basic_test.check(b):
      return  all( t.check(b) for t in self.tests)
    else:
      return False


################################################################################
# Backups hold specs about the storage of the backup to be validated,
# and other data like name and description.
# It initialises the validators defined for it in the yaml file
class Backup:
  def __init__(self, yml):
    self.location = yml['location']
    self.name     = yml["name"]
    self.validators = [self.initialize_validator(v) for v in yml["validators"]]
    self.messages = []
    self.status = 'unchecked'
  def initialize_validator(self,v):
    return Validator(v)
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
    s= "Backup " + self.name + " : " + self.status +"\n"
    for success,m in self.messages:
      s+=m+"\n"
    return s

# TODO NEXT : move the kind attribute to the back level from the validator level
# rename location to path in the yaml, and let the location be set in the backup 
# object to the real location of the file
# Maybe (?) add handle to the file in the backup instance?
# that would be handle to local file or to the s3 key of the backup file

class BackupChecker:
  def __init__(self,config_file):
    # Read config and initialise backup instances
    self.config = yaml.load(Template(file=config_file).__str__())
    self.backups= [Backup(b) for b in self.config['backups']]

  def check_backup(self,b):
    # Check one backup

    # INIT
    # i is index, l length of validators list
    i=0
    l=len(b.validators)
    
    # INV : 
    #  0<=i<l
    #  for 0<=j<i,   b.validators[j] was tested
    while i<l and not b.is_invalid():
      v=b.validators[i]
      # if the check fails; we set the backup as invalid
      # and loop will stop
      if not v.check(b):
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

bc=BackupChecker("demo.yml")
bc.check()
print bc
