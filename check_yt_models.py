# -*- coding: utf-8 -*-
from pony import orm
import pony.orm.dbproviders.sqlite
import datetime
#orm.set_sql_debug(True)

db = orm.Database()


@db.on_connect(provider='sqlite')
def sqlite_case_sensitivity(db, connection):
    cursor = connection.cursor()
    cursor.execute('PRAGMA case_sensitive_like = OFF')

db.bind(provider='sqlite', filename='checkytdb.sqlite', create_db=True)


class CheckData(db.Entity):
	dt = orm.Required(datetime.datetime, default=datetime.datetime.now())
	url = orm.Optional(str)
	data = orm.Optional(orm.Json)

class TagSEO(db.Entity):
	dt = orm.Required(datetime.datetime, default=datetime.datetime.now())
	vid = orm.Required(str)
	url = orm.Required(str)
	tag = orm.Required(str)
	seo = orm.Optional(float)
	real = orm.Optional(float)
	tcount = orm.Optional(int)
	tpopular = orm.Optional(int)
	tintitle = orm.Optional(int)
	tindesc = orm.Optional(int)
	triple = orm.Optional(int)
	tshow = orm.Optional(float)
	ranked = orm.Optional(int)
	hivolume = orm.Optional(float)
	data = orm.Optional(orm.Json)

class TagUpdate(db.Entity):
	dt = orm.Required(datetime.datetime, default=datetime.datetime.now())
	vid = orm.Required(str)
	tags1 = orm.Required(str)
	real1 = orm.Optional(float)
	tshow1 = orm.Optional(float)
	tags2 = orm.Required(str)
	real2 = orm.Optional(float)
	tshow2 = orm.Optional(float)
	jdata = orm.Optional(orm.Json)
	saved = orm.Optional(int)

class TagImport(db.Entity):
	url = orm.Required(str)
	tag = orm.Required(str)
	ttype = orm.Required(str)
	# дата не нужна, потому что будет использоваться дата в таблице TagSEO

class TagSEOArch(db.Entity):
	dt = orm.Required(datetime.datetime, default=datetime.datetime.now())
	vid = orm.Required(str)
	url = orm.Required(str)
	tag = orm.Required(str)
	seo = orm.Optional(float)
	real = orm.Optional(float)
	tcount = orm.Optional(int)
	tpopular = orm.Optional(int)
	tintitle = orm.Optional(int)
	tindesc = orm.Optional(int)
	triple = orm.Optional(int)
	tshow = orm.Optional(float)
	ranked = orm.Optional(int)
	hivolume = orm.Optional(float)
	data = orm.Optional(orm.Json)

db.generate_mapping(create_tables=True)
