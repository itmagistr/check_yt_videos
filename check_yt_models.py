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


db.generate_mapping(create_tables=True)
