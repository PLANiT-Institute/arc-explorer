from types import SimpleNamespace

import pytest
from arc_explorer.explorer_service import Explorer
from arc_explorer.sql_guard import SqlNotAllowed

CATALOGUE = {"tables": [{"TABLE_NAME": "COMPANY", "COMMENT": "Companies"}], "columns": [
    {"TABLE_NAME": "COMPANY", "COLUMN_NAME": "NAME", "DATA_TYPE": "TEXT"},
    {"TABLE_NAME": "COMPANY", "COLUMN_NAME": "SCORE", "DATA_TYPE": "NUMBER"}]}

class Connection:
    def __init__(self): self.calls=[]
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,params): self.calls.append((sql,params))
    def fetchmany(self,count): return [["Alpha",1],["Beta",2],["Gamma",3]][:count]

def settings(tmp_path):
    return SimpleNamespace(account="test", user="tester", role="read",database="DB",schema="SC",max_rows=2,schema_cache_path=tmp_path/'cache.json')

def test_filters_are_bound_and_identifiers_allowlisted(tmp_path):
    conn=Connection();e=Explorer(conn,settings(tmp_path),CATALOGUE)
    injection="'; DROP TABLE COMPANY; --"
    e.query({"table":"COMPANY","filters":[{"column":"NAME","operator":"=","value":injection}]})
    sql,params=conn.calls[-1]
    assert injection not in sql and injection in params
    with pytest.raises(ValueError): e.query({"table":"COMPANY; DROP X"})
    with pytest.raises(ValueError): e.query({"table":"COMPANY","columns":["missing"]})
    with pytest.raises(ValueError): e.query({"table":"COMPANY","sort":"missing"})
    e.close()

def test_two_snapshots_survive_reopen_and_report_truncation(tmp_path):
    s=settings(tmp_path);e=Explorer(Connection(),s,CATALOGUE)
    first=e.query({"table":"COMPANY","name":"First"},save=True)
    second=e.query({"table":"COMPANY","name":"Second"},save=True)
    assert first['id']!=second['id'] and first['has_more']
    assert len(first['rows'])==2
    e.close();restored=Explorer(Connection(),s,CATALOGUE)
    assert len(restored.saved())==2
    assert restored.saved(first['id'])['rows']==first['rows']
    restored.close()

def test_account_scope_and_pagination(tmp_path):
    s=settings(tmp_path);c=Connection();e=Explorer(c,s,CATALOGUE)
    e.query({'table':'COMPANY','offset':100,'limit':100})
    assert 'LIMIT 101 OFFSET 100' in c.calls[-1][0]
    e.query({'table':'COMPANY'},save=True);e.close()
    s.user='someone-else';other=Explorer(Connection(),s,CATALOGUE)
    assert other.saved()==[]
    other.close()


class SqlConnection(Connection):
    """Raw SQL runs without bind parameters and reports its own column names."""
    description = (("NAME",), ("SCORE",))
    def execute(self, sql, params=None): self.calls.append((sql, params))

def test_raw_sql_gets_a_limit_and_columns_from_the_cursor(tmp_path):
    conn=SqlConnection();e=Explorer(conn,settings(tmp_path),CATALOGUE)
    result=e.run_sql("SELECT NAME, SCORE FROM DB.SC.COMPANY")
    assert result['columns']==["NAME","SCORE"]
    assert "LIMIT 2" in conn.calls[-1][0]          # settings.max_rows caps the default
    assert result['executed'] and result['has_more'] and len(result['rows'])==2
    e.close()

@pytest.mark.parametrize("statement",[
    "DELETE FROM DB.SC.COMPANY","DROP TABLE DB.SC.COMPANY",
    "INSERT INTO DB.SC.COMPANY VALUES (1)","SELECT 1; DROP TABLE DB.SC.COMPANY",
    "WITH x AS (SELECT 1) UPDATE DB.SC.COMPANY SET NAME='a'"])
def test_raw_sql_rejects_anything_that_writes(tmp_path,statement):
    e=Explorer(SqlConnection(),settings(tmp_path),CATALOGUE)
    with pytest.raises(SqlNotAllowed): e.run_sql(statement)
    e.close()

def test_raw_sql_keeps_its_own_limit_and_saves_a_refreshable_snapshot(tmp_path):
    conn=SqlConnection();e=Explorer(conn,settings(tmp_path),CATALOGUE)
    result=e.run_sql("SELECT NAME FROM DB.SC.COMPANY LIMIT 1",save=True,name="mine")
    assert result['had_own_limit'] and result['limit_applied'] is None
    assert conn.calls[-1][0].count("LIMIT")==1
    assert e.saved(result['id'])['spec']=={"_kind":"sql","sql":"SELECT NAME FROM DB.SC.COMPANY LIMIT 1","limit":100}
    e.close()
