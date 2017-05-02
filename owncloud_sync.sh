#!/bin/bash

script_path="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"    

user=$1
pass=$2
local_file_path=$3
cloud_dir=$4
server="https://datacloud.ipvisionsoft.com"

read_dom () {
    local IFS=\>
    read -d \< ENTITY CONTENT
}

function url_exists {
    url=$(curl -s -X PROPFIND -u $user:$pass "$server/remote.php/dav/files/$user/$cloud_dir/")
    echo $url
}

function create_directory {
    curl -X MKCOL -u $user:$pass "$server/remote.php/dav/files/$user/$(date '+%d-%b-%Y')"
}

#Upload multiple files to owncloud
function upload_dir {
    for entry in "$local_file_path"/*
    do
	echo "Uploading file: $entry"
        curl -u $user:$pass -T $entry "$server/remote.php/dav/files/$user/$cloud_dir/"
    done
}

#Upload single file to owncloud
function upload_single_file {
    testfile="$local_file_path/joker.jpg"
    echo "Uploading $testfile"
    curl -u $user:$pass -T $testfile "$server/remote.php/dav/files/$user/$cloud_dir/"
    #curl -u $user:$pass -T $testfile "https://$server/remote.php/webdav/$cloud_dir"
}

#Get a listing of directory and files and then download the directory
function download_dirs {
    cd $local_file_path
    curl -X PROPFIND -u $user:$pass -d '<?xml version="1.0"?><d:propfind  xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
    <d:prop>
    <d:getlastmodified />
    <d:getetag />
    <d:getcontenttype />
    <d:resourcetype />
    <oc:fileid />
    <oc:permissions />
    <oc:size />
    <d:getcontentlength />
    <oc:tags />
    <oc:favorite />
    <oc:owner-display-name />
    <oc:share-types />
    <oc:comments-unread/>
    </d:prop>
    </d:propfind>' "$server/remote.php/dav/files/$user/$cloud_dir/" -o output.xml
    while read_dom; do
        if [[ $ENTITY = "d:href" ]]; then
            echo $CONTENT
        fi
    done < output.xml > fileurls.txt

    while IFS= read line; do
        if [[ "$line" == */ ]]
        then
	        echo "Directory: $line"
#	        dirname=$(echo $line | rev | cut -d'/' -f 2 | rev)
	        dirname=$(basename $line)
	        if [ ! -d $dirname ];
	        then
	            echo "Creating directory: $dirname"
	            mkdir -p $dirname
	        else
	            echo "Directory Exists: $dirname"
	        fi
	        cd $dirname
	        pwd
        else
#	        echo "File: $line"
#	        filename=$(echo $line | rev | cut -d'/' -f 1 | rev)
	        filename=$(basename $line)
	        if [ ! -f $filename ];
	        then
	            echo "Downloading file: $filename"
	            curl -X GET -u $user:$pass "$server/$line" -o $filename
	        else
                echo "$filename -- Checking..."
		        remote_hash=$(curl -# -u $user:$pass "$server/$line" | md5sum | awk '{print $1}')	
                local_hash=$(md5sum $filename | awk '{print $1}')
                if [[ "$remote_hash" != "$local_hash" ]]
                then
                    echo "Updating file: $filename"
                    curl -X GET -u $user:$pass "$server/$line" -o $filename
                fi
	        fi
        fi
    done < fileurls.txt 
#    cd $local_file_path
#    rm output.xml fileurls.txt
}

#url_exists
download_dirs
#upload_dir
#upload_single_file
echo $HOME
echo $script_path
cd $script_path
#rm output.xml fileurls.txt
exit
