#!/usr/bin/env python

from Cheetah.Template import Template
import os.path
import humanfriendly
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
    self.prepare()
  def prepare(self):
  # Used in derived classes to setup the instance more
  # precisely
    pass
  def check(self,b):
    pass

# Preliminary tests for a local file backup.
class FileTest(Test):
  def check(self,b):
    return os.path.isfile(b.location)

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
    
  def check(self,b):
    self.size=os.path.getsize(b.location)
    if self.size>=self.minsize:
      b.log_message(True, "Minimum size respected ( "+ str(self.size) +" !< " + str(self.minsize) +" ).")
      return True
    else:
      b.log_message(False, "Minimum size not respected ( "+ str(self.size) +" < " + str(self.minsize) +" ).")
      return False


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
    print "validation"
    self.status='valid'
  def set_invalid(self):
    print "invalidation"
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


class BackupChecker:
  def __init__(self,config_file):
    # Read config and initialise backup instances
    self.config = yaml.load(Template(file=config_file).__str__())
    self.backups= (Backup(b) for b in self.config['backups'])

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
      print i
      print backup.name
      print backup.status
      self.check_backup(backup)
      print backup


bc=BackupChecker("demo.yml")
bc.check()
