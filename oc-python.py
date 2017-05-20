import urllib2, urllib
import xml.etree.ElementTree as ET
import os.path
import os
import hashlib
import sqlite3 as database
from os.path import basename, isfile, join, normpath
import argparse

SERVER = 'https://example.owncloud.com'

def initialize_db(db_file):
    connection = database.connect(db_file)
    cur = connection.cursor()
    return connection,cur

def create_table(connection,cursor,table_name):
    cursor.execute('CREATE TABLE %s (fileid long, etag str, remote '
                   'int, filename str, md5sum str)' % table_name)

def get_data(conn,cur):
    cur.execute('SELECT * from sync_data')
    return cur.fetchall()

def get_single_item(conn, cur, fileid):
    cur.execute('SELECT * from sync_data where fileid=?', (fileid,))
    return cur.fetchone()

def close(connection):

    connection.commit()
    connection.close()

def insert_into_db(connection,cursor,fileid,etag,remote,filename,md5sum):
    cursor.execute('INSERT into sync_data VALUES (?, ?, ?, ?,?)',
                   (fileid,etag,remote,filename,md5sum,))

    connection.commit()

def delete_entry(connection,cursor,fileid):
    cursor.execute('DELETE from sync_data where fileid=?',(fileid,))
    connection.commit()

def update_etag(connection,cursor,fileid,etag):
    cursor.execute('UPDATE sync_data SET etag=? where fileid=?', (etag,fileid,))
    connection.commit()

def update_filename_by_id(connection,cursor,fileid,filename):
    cursor.execute('UPDATE sync_data SET filename=? where fileid=?', (filename,fileid,))
    connection.commit()

def update_md5sum(conn,cur,fileid,md5sum):
    cur.execute('UPDATE sync_data SET md5sum=? where fileid=?',(md5sum,fileid,))
    conn.commit()

def reset_db_remote(conn,cursor):
    cursor.execute('UPDATE sync_data SET remote=?',(0,))
    conn.commit()

def update_db_remote(conn,cursor,fileid):
    cursor.execute('UPDATE sync_data SET remote=? where fileid=?',(1,fileid))
    conn.commit()

def fetch_etag_by_fileid(cursor, fileid):
    cursor.execute('SELECT etag from sync_data where fileid=?',(fileid,))
    return cursor.fetchone()

def fetch_md5_by_filename(cursor, filename):
    cursor.execute('SELECT md5sum from sync_data where filename=?',(filename,))
    return cursor.fetchone()

def fetch_info_by_md5(cursor, local_md5):
    cursor.execute('SELECT * from sync_data where md5sum=?',(local_md5,))
    return cursor.fetchone()

def build_request(user, password, method, end_point, xml_data="",header=None):
    auth_info = urllib2.HTTPPasswordMgrWithDefaultRealm()
    auth_info.add_password(None,SERVER,user,password)
    page = SERVER + end_point
    handler = urllib2.HTTPBasicAuthHandler(auth_info)
    myopener = urllib2.build_opener(handler)
    urllib2.install_opener(myopener)
    xml_data = xml_data
    if header is not None:
        request = urllib2.Request(url=page, data=xml_data, headers=header)
    else:
        request = urllib2.Request(url=page, data=xml_data)
    request.get_method = lambda: method
    try:
        output = urllib2.urlopen(request)
        return output.read()
    except urllib2.URLError as e:
        print e
        return None

def get_metadata(user, password, remote_dir, filename=None):
    if filename is None:
        url = "/remote.php/dav/files/" + user + remote_dir
    else:
        url = "/remote.php/dav/files/" + user + remote_dir + filename

    data_xml = '<?xml version="1.0"?><d:propfind  xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:prop><d:getlastmodified /><d:getetag /><d:getcontenttype /><d:resourcetype /><oc:fileid /><oc:permissions /><oc:size /><d:getcontentlength /><oc:tags /><oc:favorite /><oc:owner-display-name /><oc:share-types /><oc:comments-unread/></d:prop></d:propfind>'
    header = {'Content-Type':'application/xml'}
    result_xml = build_request(user,password,'PROPFIND',url,data_xml,header)
    return result_xml
    tree = ET.fromstring(result_xml)
    return tree

def get_item_from_xml(metadata_xml):
    #url_list = [ch.text for child in metadata_xml for ch in child if ch.tag == '{DAV:}href']
    metadata_xml = ET.fromstring(metadata_xml)
    data_list = []
    for response in metadata_xml:
        temp_list = []
        temp_list.append(response[0].text)
        for tags in response[1][0]:
            if tags.tag == '{http://owncloud.org/ns}fileid':
                temp_list.append(tags.text)
            elif tags.tag == '{DAV:}getetag':
                temp_list.append(tags.text)
        data_list.append(temp_list)
    return data_list

def save_file(url, user, password):
    result_img = build_request(user, password, 'GET', url)
    filename = os.path.basename(url)
    f = open(filename,'wb')
    f.write(result_img)
    f.close()

def file_exists(filename):
    return os.path.isfile(filename)

def get_md5_checksum(filename):
    return hashlib.md5(open(filename, 'rb').read()).hexdigest()

def clean_local(conn, cur, local_dir, remote_dir):
    fullpath = local_dir + basename(normpath(remote_dir)) + '/'
    print "removing deleted files"
    cur.execute('SELECT * from sync_data where remote=?', (0,))
    result = cur.fetchall()
    for files in result:
        if os.path.isfile(fullpath + files[3]):
            print "removing file: %s" % files[3]
            os.remove(fullpath + files[3])
    cur.execute('DELETE from sync_data where remote=?',(0,))
    conn.commit()

def download_dir(user, password, conn, cur, local_dir, remote_dir):
    """Download files from remote server
    Store metadata in sqlite database
    """
    print "Checking remote server"
    reset_db_remote(conn, cur)
    metadata_xml = get_metadata(user, password, remote_dir)
    item_list = get_item_from_xml(metadata_xml)
    for items in item_list:
        update_db_remote(conn, cur, items[2])
        val = items[0][-1:]
        if val == '/':
            dirname = items[0].rsplit('/', 2)[1]
            if not os.path.exists(local_dir + dirname):
                os.mkdir(local_dir + dirname)
            os.chdir(local_dir + dirname)
        else:
            #file_etag = fetch_etag_by_fileid(cur, items[2])
            file_db_info = get_single_item(conn, cur, items[2])
            if file_db_info is None:
                print "Downloading file: %s" % basename(items[0])
                save_file(items[0], user, password)
                md5sum = get_md5_checksum(basename(items[0]))
                insert_into_db(conn, cur,
                               items[2], items[1], 1, basename(items[0]), md5sum)
            else:
                if os.path.isfile((basename(items[0]))):
                    if file_db_info[1] == items[1]:
                        print "File not changed: %s"% basename(items[0])
                    else:
                        print "Updating file: %s"% os.path.basename(items[0])
                        save_file(items[0], user, password)
                        md5sum = get_md5_checksum(basename(items[0]))
                        update_etag(conn, cur, items[2], items[1])
                        update_md5sum(conn, cur, items[2], md5sum)
                else:
                    if os.path.isfile(file_db_info[3]):
                        if file_db_info[1] == items[1]:
                            print "File renamed, updating: %s"% basename(items[0])
                            os.rename(file_db_info[3], basename(items[0]))
                            update_filename_by_id(conn, cur, items[2], basename(items[0]))
                        else:
                            print "File renamed and changed,updating: %s" % basename(items[0])
                            os.remove(file_db_info[3])
                            save_file(items[0], user, password)
                            delete_entry(conn, cur, items[2])
                            md5sum = get_md5_checksum(basename(items[0]))
                            insert_into_db(conn, cur, items[2], items[1], 1, basename(items[0]), md5sum)
                    else:
                        print "File deleted,downloading: %s" % basename(items[0])
                        save_file(items[0], user, password)
                        delete_entry(conn, cur, items[2])
                        md5sum = get_md5_checksum(basename(items[0]))
                        insert_into_db(conn, cur, items[2], items[1], 1, basename(items[0]), md5sum)

def update_entry(conn, cur, user, password, filename, local_md5, remote_dir):
    file_xml = get_metadata(user, password, remote_dir, filename)
    prop = get_item_from_xml(file_xml)
    delete_entry(conn,cur,prop[0][2])
    insert_into_db(conn,cur,prop[0][2],prop[0][1],1,filename,local_md5)

def upload_file(user, password, local_dir, remote_dir, filename):
    fullpath = local_dir + basename(normpath(remote_dir)) + '/'
    url = '/remote.php/dav/files/' + user + remote_dir + filename
    result = build_request(user, password, 'PUT', url,
                           open(fullpath+filename,'r').read())

def rename_file_remote(user, password, remote_dir, n_file, o_file):
    url = '/remote.php/dav/files/' + user + remote_dir + o_file
    header = {'Destination': SERVER + '/remote.php/dav/files/' + user +
              remote_dir + n_file}
    build_request(user, password, 'MOVE', url, '', header)

def upload_files(user, password, conn, cur, local_dir, remote_dir):
    print "Checking local"
    fullpath = local_dir + basename(normpath(remote_dir)) + '/'
    if not os.path.isdir(fullpath):
        os.mkdir(fullpath)
    files = [f for f in os.listdir(fullpath) if isfile(join(fullpath,f))]
    for filename in files:
        remote_md5 = fetch_md5_by_filename(cur,filename)
        local_md5 = hashlib.md5(open(fullpath+filename,'rb').read()).hexdigest()
        if remote_md5 is None:
            file_info = fetch_info_by_md5(cur, local_md5)
            if file_info is None:
                print "Uploading file: %s" % filename
                upload_file(user, password, local_dir, remote_dir, filename)
                update_entry(conn, cur, user,password, filename, local_md5, remote_dir)
            else:
                print 'Renaming file'
                rename_file_remote(user, password, remote_dir, filename, file_info[3])
                update_filename_by_id(conn, cur, file_info[0], filename)
        else:
            if remote_md5[0] == local_md5:
                print "File not changed: %s" % filename
            else:
                print "Updating file: %s" % filename
                upload_file(user, password, local_dir, remote_dir, filename)
                update_entry(conn, cur, user, password, filename, local_md5, remote_dir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("username", help="Provide an owncloud username")
    parser.add_argument("password", help="Provide an owncloud password")
    parser.add_argument("local", help="Local Directory for owncloud sync")
    parser.add_argument("remote", help="Remote Owncloud Directory")
    args = parser.parse_args()
    username, password, local_dir, remote_dir = args.username, args.password, args.local, args.remote

    sqlite_file = '.oc-database.sqlite'
    table_name = 'sync_data'
    conn, cur = initialize_db(sqlite_file)
    tb_exists = "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_data'"
    first_time = False
    if not conn.execute(tb_exists).fetchone():
        create_table(conn,cur,table_name)
        first_time = True
    conn.commit()
    if first_time:
        download_dir(username, password, conn, cur, local_dir, remote_dir)
        clean_local(conn,cur, local_dir, remote_dir)
        upload_files(username, password, conn, cur, local_dir, remote_dir)
    else:
        upload_files(username, password, conn, cur, local_dir, remote_dir)
        download_dir(username, password, conn, cur, local_dir, remote_dir)
        clean_local(conn,cur, local_dir, remote_dir)
        upload_files(username, password, conn, cur, local_dir, remote_dir)
    #print get_data(conn,cur)
    close(conn)
    print "Done....."
