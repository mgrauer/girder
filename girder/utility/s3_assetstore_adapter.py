#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright 2014 Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import boto
import boto.s3.connection
import cherrypy
import json
import re
import requests
import six
import uuid

from .abstract_assetstore_adapter import AbstractAssetstoreAdapter
from girder.models.model_base import ValidationException
from girder import logger, events


class S3AssetstoreAdapter(AbstractAssetstoreAdapter):
    """
    This assetstore type stores files on S3. It is responsible for generating
    HMAC-signed messages that authorize the client to communicate directly with
    the S3 server where the files are stored.
    """

    CHUNK_LEN = 1024 * 1024 * 32  # Chunk size for uploading
    HMAC_TTL = 120  # Number of seconds each signed message is valid

    @staticmethod
    def fileIndexFields():
        """
        File documents should have an index on their verified field.
        """
        return ['s3Verified']

    @staticmethod
    def validateInfo(doc):
        """
        Makes sure the root field is a valid absolute path and is writeable.
        """
        if 'prefix' not in doc:
            doc['prefix'] = ''
        # remove slashes from front and back of the prefix
        doc['prefix'] = doc['prefix'].strip('/')
        if not doc.get('bucket'):
            raise ValidationException('Bucket must not be empty.', 'bucket')
        if not doc.get('readOnly'):
            if not doc.get('secret'):
                raise ValidationException(
                    'Secret key must not be empty.', 'secret')
            if not doc.get('accessKeyId'):
                raise ValidationException(
                    'Access key ID must not be empty.', 'accessKeyId')
        # construct a set of connection parameters based on the keys and the
        # service
        if 'service' not in doc:
            doc['service'] = ''
        if doc['service'] != '':
            service = re.match("^((https?)://)?([^:/]+)(:([0-9]+))?$",
                               doc['service'])
            if not service:
                raise ValidationException(
                    'The service must of the form [http[s]://](host domain)'
                    '[:(port)].', 'service')
        doc['botoConnect'] = makeBotoConnectParams(
            doc['accessKeyId'], doc['secret'], doc['service'])
        # Make sure we can write into the given bucket using boto
        conn = botoConnectS3(doc['botoConnect'])
        if doc.get('readOnly'):
            try:
                conn.get_bucket(bucket_name=doc['bucket'], validate=True)
            except Exception:
                logger.exception('S3 assetstore validation exception')
                raise ValidationException('Unable to connect to bucket "{}".'
                                          .format(doc['bucket']), 'bucket')
        else:
            try:
                bucket = conn.get_bucket(bucket_name=doc['bucket'],
                                         validate=True)
                testKey = boto.s3.key.Key(
                    bucket=bucket, name='/'.join(
                        filter(None, (doc['prefix'], 'test'))))
                testKey.set_contents_from_string('')
            except Exception:
                logger.exception('S3 assetstore validation exception')
                raise ValidationException('Unable to write into bucket "{}".'
                                          .format(doc['bucket']), 'bucket')

        return doc

    def __init__(self, assetstore):
        """
        :param assetstore: The assetstore to act on.
        """
        if ('accessKeyId' in assetstore and 'secret' in assetstore and
                'service' in assetstore):
            assetstore['botoConnect'] = makeBotoConnectParams(
                assetstore['accessKeyId'], assetstore['secret'],
                assetstore['service'])
        self.assetstore = assetstore

    def _getRequestHeaders(self, upload):
        return {
            'Content-Disposition': 'attachment; filename="{}"'
                                   .format(upload['name']),
            'Content-Type': upload.get('mimeType', ''),
            'x-amz-acl': 'private',
            'x-amz-meta-authorized-length': str(upload['size']),
            'x-amz-meta-uploader-id': str(upload['userId']),
            'x-amz-meta-uploader-ip': str(cherrypy.request.remote.ip)
        }

    def initUpload(self, upload):
        """
        Build the request required to initiate an authorized upload to S3.
        """
        if upload['size'] <= 0:
            return upload

        uid = uuid.uuid4().hex
        key = '/'.join(filter(None, (self.assetstore.get('prefix', ''),
                       uid[0:2], uid[2:4], uid)))
        path = '/{}/{}'.format(self.assetstore['bucket'], key)
        headers = self._getRequestHeaders(upload)

        chunked = upload['size'] > self.CHUNK_LEN

        upload['behavior'] = 's3'
        upload['s3'] = {
            'chunked': chunked,
            'chunkLength': self.CHUNK_LEN,
            'relpath': path,
            'key': key
        }

        if chunked:
            upload['s3']['request'] = {'method': 'POST'}
            queryParams = 'uploads'
        else:
            upload['s3']['request'] = {'method': 'PUT'}
            queryParams = None
        url = self._botoGenerateUrl(
            method=upload['s3']['request']['method'], key=key, headers=headers,
            queryParams=queryParams)
        upload['s3']['request']['url'] = url
        upload['s3']['request']['headers'] = headers
        return upload

    def uploadChunk(self, upload, chunk):
        """
        Rather than processing actual bytes of the chunk, this will generate
        the signature required to upload the chunk. Clients that do not support
        direct-to-S3 upload can pass the chunk via the request body as with
        other assetstores, and girder will proxy the data through to S3.

        :param chunk: This should be a JSON string containing the chunk number
            and S3 upload ID. If a normal chunk file-like object is passed,
            we will send the data to S3.
        """
        if isinstance(chunk, six.string_types):
            return self._clientUploadChunk(upload, chunk)
        else:
            return self._proxiedUploadChunk(upload, chunk)

    def _clientUploadChunk(self, upload, chunk):
        """
        Clients that support direct-to-S3 upload behavior will go through this
        method by sending a normally-encoded form string as the chunk parameter,
        containing the required JSON info for uploading. This generates the
        signed URL that the client should use to upload the chunk to S3.
        """
        info = json.loads(chunk)
        queryStr = 'partNumber={}&uploadId={}'.format(info['partNumber'],
                                                      info['s3UploadId'])
        url = self._botoGenerateUrl(method='PUT', key=upload['s3']['key'],
                                    queryParams=queryStr)

        upload['s3']['uploadId'] = info['s3UploadId']
        upload['s3']['partNumber'] = info['partNumber']
        upload['s3']['request'] = {
            'method': 'PUT',
            'url': url
        }

        return upload

    def _getBucket(self, validate=True):
        conn = botoConnectS3(self.assetstore['botoConnect'])
        bucket = conn.lookup(bucket_name=self.assetstore['bucket'],
                             validate=validate)

        if not bucket:
            raise Exception('Could not connect to S3 bucket.')

        return bucket

    def _proxiedUploadChunk(self, upload, chunk):
        """
        Clients that do not support direct-to-S3 upload behavior will go through
        this method by sending the chunk as a multipart-encoded file parameter
        as they would with other assetstore types. Girder will send the data
        to S3 on behalf of the client.
        """
        bucket = self._getBucket()

        if upload['s3']['chunked']:
            if 'uploadId' in upload['s3']:
                mp = boto.s3.multipart.MultiPartUpload(bucket)
                mp.id = upload['s3']['uploadId']
                mp.key_name = upload['s3']['keyName']
            else:
                mp = bucket.initiate_multipart_upload(
                    upload['s3']['key'],
                    headers=self._getRequestHeaders(upload))
                upload['s3']['uploadId'] = mp.id
                upload['s3']['keyName'] = mp.key_name
                upload['s3']['partNumber'] = 0

            upload['s3']['partNumber'] += 1

            key = mp.upload_part_from_file(
                chunk, upload['s3']['partNumber'],
                headers=self._getRequestHeaders(upload))
            upload['received'] += key.size
        else:
            key = bucket.new_key(upload['s3']['key'])
            key.set_contents_from_file(chunk,
                                       headers=self._getRequestHeaders(upload))

            if key.size < upload['size']:
                bucket.delete_key(key)
                raise ValidationException('Uploads of this length must be sent '
                                          'in a single chunk.')

            upload['received'] = key.size

        return upload

    def requestOffset(self, upload):
        if upload['received'] > 0:
            # This is only set when we are proxying the data to S3
            return upload['received']

        if upload['s3']['chunked']:
            raise ValidationException(
                'You should not call requestOffset on a chunked direct-to-S3 '
                'upload.')

        headers = self._getRequestHeaders(upload)
        url = self._botoGenerateUrl(method='PUT', key=upload['s3']['key'],
                                    headers=headers)
        return {
            'method': 'PUT',
            'url': url,
            'headers': headers,
            'offset': 0
        }

    def finalizeUpload(self, upload, file):
        if upload['size'] <= 0:
            return file

        file['relpath'] = upload['s3']['relpath']
        file['s3Key'] = upload['s3']['key']
        file['s3Verified'] = False

        if upload['s3']['chunked']:
            if upload['received'] > 0:
                # We proxied the data to S3
                bucket = self._getBucket()
                mp = boto.s3.multipart.MultiPartUpload(bucket)
                mp.id = upload['s3']['uploadId']
                mp.key_name = upload['s3']['keyName']
                mp.complete_upload()
            else:
                queryStr = 'uploadId=' + upload['s3']['uploadId']
                headers = {'Content-Type': 'text/plain;charset=UTF-8'}
                url = self._botoGenerateUrl(
                    method='POST', key=upload['s3']['key'], headers=headers,
                    queryParams=queryStr)
                file['s3FinalizeRequest'] = {
                    'method': 'POST',
                    'url': url,
                    'headers': headers
                }
        return file

    def downloadFile(self, file, offset=0, headers=True):
        """
        When downloading a single file with HTTP, we redirect to S3. Otherwise,
        e.g. when downloading as part of a zip stream, we connect to S3 and
        pipe the bytes from S3 through the server to the user agent.
        """
        if self.assetstore.get('botoConnect', {}).get('anon') is True:
            urlFn = self._anonDownloadUrl
        else:
            urlFn = self._botoGenerateUrl

        if headers:
            if file['size'] > 0:
                url = urlFn(key=file['s3Key'])
                raise cherrypy.HTTPRedirect(url)
            else:
                cherrypy.response.headers['Content-Length'] = '0'
                cherrypy.response.headers['Content-Type'] = \
                    'application/octet-stream'
                cherrypy.response.headers['Content-Disposition'] = \
                    'attachment; filename="{}"'.format(file['name'])

                def stream():
                    yield ''
                return stream
        else:
            def stream():
                if file['size'] > 0:
                    pipe = requests.get(urlFn(key=file['s3Key']), stream=True)
                    for chunk in pipe.iter_content(chunk_size=65536):
                        if chunk:
                            yield chunk
                else:
                    yield ''
            return stream

    def importData(self, parent, parentType, params, progress, user,
                   bucket=None):
        importPath = params.get('importPath', '').strip().lstrip('/')

        if importPath and not importPath.endswith('/'):
            importPath += '/'

        if bucket is None:
            bucket = self._getBucket()

        for obj in bucket.list(importPath, '/'):
            if progress:
                progress.update(message=obj.name)

            if isinstance(obj, boto.s3.prefix.Prefix):
                name = obj.name.rstrip('/').rsplit('/', 1)[-1]
                folder = self.model('folder').createFolder(
                    parent=parent, name=name, parentType=parentType,
                    creator=user, reuseExisting=True)
                self.importData(parent=folder, parentType='folder', params={
                    'importPath': obj.name
                }, progress=progress, user=user, bucket=bucket)
            elif isinstance(obj, boto.s3.key.Key):
                name = obj.name.rsplit('/', 1)[-1]
                if not name:
                    continue

                if parentType != 'folder':
                    raise ValidationException(
                        'Keys cannot be imported directly underneath a %s.' %
                        parentType)

                item = self.model('item').createItem(
                    name=name, creator=user, folder=parent, reuseExisting=True)
                file = self.model('file').createFile(
                    name=name, creator=user, item=item, reuseExisting=True,
                    assetstore=self.assetstore, mimeType=None, size=obj.size)
                file['s3Key'] = obj.name
                file['imported'] = True
                self.model('file').save(file)

    def deleteFile(self, file):
        """
        We want to queue up files to be deleted asynchronously since it requires
        an external HTTP request per file in order to delete them, and we don't
        want to wait on that.

        Files that were imported as pre-existing data will not actually be
        deleted from S3, only their references in Girder will be deleted.
        """
        if file['size'] > 0 and 'relpath' in file:
            q = {
                'relpath': file['relpath'],
                'assetstoreId': self.assetstore['_id']
            }
            matching = self.model('file').find(q, limit=2, fields=[])
            if matching.count(True) == 1:
                events.daemon.trigger('_s3_assetstore_delete_file', {
                    'botoConnect': self.assetstore.get('botoConnect', {}),
                    'bucket': self.assetstore['bucket'],
                    'key': file['s3Key']
                })

    def cancelUpload(self, upload):
        """
        Delete the temporary files associated with a given upload.
        """
        if 's3' not in upload:
            return
        if 'key' not in upload['s3']:
            return

        bucket = self._getBucket()
        if bucket:
            key = bucket.get_key(upload['s3']['key'], validate=True)
            if key:
                bucket.delete_key(key)
            # check if this is an abandoned multipart upload
            if ('s3' in upload and 'uploadId' in upload['s3'] and
                    'key' in upload['s3']):
                getParams = {}
                while True:
                    try:
                        multipartUploads = bucket.get_all_multipart_uploads(
                            **getParams)
                    except boto.exception.S3ResponseError:
                        break
                    if not len(multipartUploads):
                        break
                    for multipartUpload in multipartUploads:
                        if (multipartUpload.id == upload['s3']['uploadId'] and
                                multipartUpload.key_name ==
                                upload['s3']['key']):
                            multipartUpload.cancel_upload()
                    if not multipartUploads.is_truncated:
                        break
                    getParams['key_marker'] = multipartUploads.next_key_marker
                    getParams['upload_id_marker'] = \
                        multipartUploads.next_upload_id_marker

    def untrackedUploads(self, knownUploads=[], delete=False):
        """
        List and optionally discard uploads that are in the assetstore but not
        in the known list.
        :param knownUploads: a list of upload dictionaries of all known
                             incomplete uploads.
        :type knownUploads: list
        :param delete: if True, delete any unknown uploads.
        :type delete: bool
        :returns: a list of unknown uploads.
        """
        untrackedList = []
        prefix = self.assetstore.get('prefix', '')
        if prefix:
            prefix += '/'

        bucket = self._getBucket()
        if not bucket:
            return []
        getParams = {}
        while True:
            try:
                multipartUploads = bucket.get_all_multipart_uploads(**getParams)
            except boto.exception.S3ResponseError:
                break
            if not len(multipartUploads):
                break
            for multipartUpload in multipartUploads:
                if self._uploadIsKnown(multipartUpload, knownUploads):
                    continue
                # don't include uploads with a different prefix; this allows a
                # single bucket to handle multiple assetstores and us to only
                # clean up the one we are in.  We could further validate that
                # the key name was of the format /(prefix)/../../(id)
                if not multipartUpload.key_name.startswith(prefix):
                    continue
                unknown = {'s3': {'uploadId': multipartUpload.id,
                                  'key': multipartUpload.key_name}}
                untrackedList.append(unknown)
                if delete:
                    multipartUpload.cancel_upload()
            if not multipartUploads.is_truncated:
                break
            getParams['key_marker'] = multipartUploads.next_key_marker
            getParams['upload_id_marker'] = \
                multipartUploads.next_upload_id_marker
        return untrackedList

    def _uploadIsKnown(self, multipartUpload, knownUploads):
        """
        Check if a multipartUpload as returned by boto is in our list of known
        uploads.
        :param multipartUpload: an upload entry from get_all_multipart_uploads.
        :param knownUploads: a list of our known uploads.
        :results: TRue if the upload is known.
        """
        for upload in knownUploads:
            if ('s3' in upload and 'uploadId' in upload['s3'] and
                    'key' in upload['s3']):
                if (multipartUpload.id == upload['s3']['uploadId'] and
                        multipartUpload.key_name == upload['s3']['key']):
                    return True
        return False

    def _botoGenerateUrl(self, key, method='GET', headers=None,
                         queryParams=None):
        """
        Generate a URL to communicate with the S3 server.  This leverages the
        boto generate_url method, but has additional parameters to compensate
        for that methods lack of exposing query parameters.

        :param method: one of 'GET', 'PUT', 'POST', or 'DELETE'.
        :param key: the name of the S3 key to use.
        :param headers: if present, a dictionary of headers to encode in the
                        request.
        :param queryParams: if present, parameters to add to the query.
        :returns: a url that can be sent with the headers to the S3 server.
        """
        conn = botoConnectS3(self.assetstore.get('botoConnect', {}))
        if queryParams:
            keyquery = key+'?'+queryParams
        else:
            keyquery = key
        url = conn.generate_url(
            expires_in=self.HMAC_TTL, method=method,
            bucket=self.assetstore['bucket'], key=keyquery, headers=headers)
        if queryParams:
            parts = url.split('?')
            if len(parts) == 3:
                config = self.assetstore.get('botoConnect', {})
                # This clause allows use to work with a moto server.  It will
                # probably do no harm in any real scenario
                if (queryParams == "uploads" and
                        not config.get('is_secure', True) and
                        config.get('host') == '127.0.0.1'):
                    url = parts[0]+'?'+parts[1]
                else:
                    url = parts[0]+'?'+parts[1]+'&'+parts[2]
        return url

    def _anonDownloadUrl(self, key):
        """
        Generate and return an anonymous download URL for the given key. This
        is necessary as a workaround for a limitation of boto's generate_url,
        documented here: https://github.com/boto/boto/issues/1540
        """
        if self.assetstore['service']:
            return '/'.join((
                self.assetstore['service'], self.assetstore['bucket'],
                key.lstrip('/')))
        else:
            service = 'https://%s.s3.amazonaws.com' % self.assetstore['bucket']
            return '/'.join((service, key.lstrip('/')))


class BotoCallingFormat(boto.s3.connection.OrdinaryCallingFormat):
    # By subclassing boto's calling format, we can pass upload parameters along
    # with the key and get it to do the work of creating urls for us.  The only
    # difference between boto's OrdinaryCallingFormat and this is that we don't
    # urllib.quote the key
    def build_auth_path(self, bucket, key=''):
        path = ''
        if bucket:
            path = '/' + bucket
        return path + '/' + key

    def build_path_base(self, bucket, key=''):
        path_base = '/'
        if bucket:
            path_base += bucket + '/'
        return path_base + key


def botoConnectS3(connectParams):
    """
    Connect to the S3 server, throwing an appropriate exception if we fail.
    :param connectParams: a dictionary of paramters to use in the connection.
    :returns: the boto connection object.
    """
    if 'anon' not in connectParams or not connectParams['anon']:
        connectParams = connectParams.copy()
        connectParams['calling_format'] = BotoCallingFormat()

    try:
        return boto.connect_s3(**connectParams)
    except Exception:
        logger.exception('S3 assetstore validation exception')
        raise ValidationException('Unable to connect to S3 assetstore')


def makeBotoConnectParams(accessKeyId, secret, service=None):
    """
    Create a dictionary of values to pass to the boto connect_s3 function.

    :param accessKeyId: the S3 access key ID
    :param secret: the S3 secret key
    :param service: the name of the service in the form
                    [http[s]://](host domain)[:(port)].
    :returns: boto connection parameter dictionary.
    """
    if accessKeyId and secret:
        connect = {
            'aws_access_key_id': accessKeyId,
            'aws_secret_access_key': secret,
            }
    else:
        connect = {
            'anon': True
        }

    if service:
        service = re.match("^((https?)://)?([^:/]+)(:([0-9]+))?$", service)
        if service.groups()[1] == 'http':
            connect['is_secure'] = False
        connect['host'] = service.groups()[2]
        if service.groups()[4] is not None:
            connect['port'] = int(service.groups()[4])
    return connect


def _deleteFileImpl(event):
    """
    Uses boto to delete the key.
    """
    info = event.info
    conn = botoConnectS3(info.get('botoConnect', {}))
    bucket = conn.lookup(bucket_name=info['bucket'], validate=False)
    key = bucket.get_key(info['key'], validate=True)
    if key:
        bucket.delete_key(key)


events.bind('_s3_assetstore_delete_file', '_s3_assetstore_delete_file',
            _deleteFileImpl)
