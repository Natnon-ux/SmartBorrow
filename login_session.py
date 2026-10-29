"""จำการล็อกอิน 12 ชั่วโมง: คุกกี้สุ่ม เก็บเฉพาะแฮช และเพิกถอนได้"""
import hashlib
import json
import secrets
import time
import streamlit as st
from database import database_connection

COOKIE='smartborrow_session'
LIFETIME=12*60*60

def table(con):
    con.execute('CREATE TABLE IF NOT EXISTS login_sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, auth_version INTEGER NOT NULL, expires_at INTEGER NOT NULL, rules_accepted INTEGER NOT NULL DEFAULT 0)')

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def issue(user,path):
    token=secrets.token_urlsafe(32)
    with database_connection(path) as con:
        table(con)
        con.execute('DELETE FROM login_sessions WHERE expires_at<=?',(int(time.time()),))
        con.execute('INSERT INTO login_sessions VALUES(?,?,?,?,0)',(digest(token),user['id'],user.get('auth_version',0),int(time.time())+LIFETIME))
    st.session_state['_login_token']=token
    st.session_state['_login_db']=str(path)
    st.session_state['_cookie_write']=token

def restore(path):
    if st.session_state.get('_restore_attempted'):return None
    st.session_state['_restore_attempted']=True
    token=st.context.cookies.get(COOKIE,'')
    if not isinstance(token,str) or not token or len(token)>128:return None
    with database_connection(path) as con:
        table(con)
        row=con.execute('SELECT s.*,u.status,u.auth_version AS current_version FROM login_sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=?',(digest(token),)).fetchone()
    if not row or row['expires_at']<=time.time() or row['status']!='active' or row['auth_version']!=row['current_version']:
        st.session_state['_cookie_write']=''
        return None
    st.session_state['_login_token']=token
    st.session_state['_login_db']=str(path)
    if row['rules_accepted']:
        st.session_state['usage_rules_accepted_for']=(row['user_id'],row['auth_version'])
    return {'id':row['user_id'],'auth_version':row['auth_version']}

def revoke():
    token=st.session_state.get('_login_token')
    path=st.session_state.get('_login_db')
    if token and path:
        with database_connection(path) as con:
            table(con)
            con.execute('DELETE FROM login_sessions WHERE token_hash=?',(digest(token),))

def accept_rules(path):
    token=st.session_state.get('_login_token')
    if token:
        with database_connection(path) as con:
            table(con)
            con.execute('UPDATE login_sessions SET rules_accepted=1 WHERE token_hash=?',(digest(token),))

def write_cookie():
    if '_cookie_write' not in st.session_state:return
    token=st.session_state.pop('_cookie_write')
    value=f'{COOKIE}={token}; Path=/; Max-Age={LIFETIME if token else 0}; SameSite=Strict'
    st.html('<script>document.cookie='+json.dumps(value)+'+(location.protocol === "https:" ? "; Secure" : "");</script>',unsafe_allow_javascript=True)
