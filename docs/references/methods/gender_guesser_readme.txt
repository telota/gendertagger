This package uses the underlying data from the program “gender” by Jorg Michael (described here). Its use is pretty straightforward:

>>> import gender_guesser.detector as gender
>>> d = gender.Detector()
>>> print(d.get_gender(u"Bob"))
male
>>> print(d.get_gender(u"Sally"))
female
>>> print(d.get_gender(u"Pauley")) # should be androgynous
andy

The result will be one of unknown (name not found), andy (androgynous), male, female, mostly_male, or mostly_female. The difference between andy and unknown is that the former is found to have the same probability to be male than to be female, while the later means that the name wasn’t found in the database.

I18N is fully supported:

>>> print(d.get_gender(u"\xc1lfr\xfan"))  # u"Álfrún"
female

Additionally, you can give preference to specific countries:

>>> print(d.get_gender(u"Jamie"))
mostly_female
>>> print(d.get_gender(u"Jamie", u'great_britain'))
mostly_male

Additionally, you can create a detector that is not case sensitive (default is to be case sensitive):

>>> d = gender.Detector(case_sensitive=False)
>>> print(d.get_gender(u"sally"))
female
>>> print(d.get_gender(u"Sally"))
female

Try to avoid creating many Detectors, as each creation means reading the data file.