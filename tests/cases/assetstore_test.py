#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright 2013 Kitware Inc.
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

import httmock
import io
import json
import mock
import moto
import os
import six
import time
import zipfile

from .. import base, mock_s3
from girder.constants import AssetstoreType, ROOT_DIR
from girder.utility.s3_assetstore_adapter import makeBotoConnectParams


def setUpModule():
    # We want to test the paths to the actual amazon S3 server, so we use
    # direct mocking rather than a local S3 server.
    base.startServer(mockS3=False)


def tearDownModule():
    base.stopServer()


class AssetstoreTestCase(base.TestCase):

    def setUp(self):
        base.TestCase.setUp(self)

        info = {
            'email': 'admin@email.com',
            'login': 'admin',
            'firstName': 'Admin',
            'lastName': 'Admin',
            'password': 'adminpassword',
            'admin': True
        }
        self.admin = self.model('user').createUser(**info)

    def testCreateAndSetCurrent(self):
        # Non admin users should not be able to see assetstore list
        resp = self.request(path='/assetstore', method='GET')
        self.assertStatus(resp, 401)

        resp = self.request(path='/assetstore', method='GET', user=self.admin)
        self.assertStatusOk(resp)
        self.assertEqual(1, len(resp.json))
        oldAssetstore = resp.json[0]

        self.assertTrue(oldAssetstore['current'])
        self.assertEqual(oldAssetstore['name'], 'Test')
        self.assertEqual(oldAssetstore['type'], AssetstoreType.FILESYSTEM)

        params = {
            'name': 'Test',
            'type': -1
        }
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatus(resp, 400)
        self.assertEqual(resp.json, {
            'type': 'rest',
            'message': 'Invalid type parameter'
        })

        params = {
            'name': 'Test',
            'type': AssetstoreType.FILESYSTEM
        }
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertMissingParameter(resp, 'root')

        params['root'] = os.path.join(oldAssetstore['root'], 'other')
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatus(resp, 400)
        self.assertEqual(resp.json['field'], 'name')

        params['name'] = 'New Name'
        # Actually creates the new assetstore
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatusOk(resp)
        assetstore = resp.json
        self.assertEqual(assetstore['name'], 'New Name')
        self.assertFalse(assetstore['current'])

        # Set the new assetstore as current
        params = {
            'name': assetstore['name'],
            'root': assetstore['root'],
            'current': True
        }
        resp = self.request(path='/assetstore/{}'.format(assetstore['_id']),
                            method='PUT', user=self.admin, params=params)
        self.assertStatusOk(resp)
        assetstore = self.model('assetstore').load(resp.json['_id'])
        self.assertTrue(assetstore['current'])

        # The old assetstore should no longer be current
        oldAssetstore = self.model('assetstore').load(oldAssetstore['_id'])
        self.assertFalse(oldAssetstore['current'])

        # List the assetstores
        assetstoresBefore = list(self.model('assetstore').list())
        # Now break the root of the new assetstore and make sure we can still
        # list it
        oldroot = assetstore['root']
        assetstore['root'] = '///invalidpath'
        self.model('assetstore').save(assetstore, validate=False)
        assetstoresAfter = list(self.model('assetstore').list())
        self.assertEqual(len(assetstoresBefore), len(assetstoresAfter))
        self.assertIsNone([
            store for store in assetstoresAfter
            if store['_id'] == assetstore['_id']][0]['capacity']['free'])
        # restore the original root
        assetstore['root'] = oldroot
        self.model('assetstore').save(assetstore, validate=False)

    def testDeleteAssetstore(self):
        resp = self.request(path='/assetstore', method='GET', user=self.admin)
        self.assertStatusOk(resp)
        self.assertEqual(1, len(resp.json))
        assetstore = self.model('assetstore').load(resp.json[0]['_id'])

        # Create a second assetstore so that when we delete the first one, the
        # current assetstore will be switched to the second one.
        secondStore = self.model('assetstore').createFilesystemAssetstore(
            'Another Store',  os.path.join(ROOT_DIR, 'tests', 'assetstore',
                                           'server_assetstore_test2'))
        # make sure our original asset store is the current one
        current = self.model('assetstore').getCurrent()
        self.assertEqual(current['_id'], assetstore['_id'])

        # Anonymous user should not be able to delete assetstores
        resp = self.request(path='/assetstore/{}'.format(assetstore['_id']),
                            method='DELETE')
        self.assertStatus(resp, 401)

        # Simulate the existence of a file within the assetstore
        folders = self.model('folder').childFolders(
            self.admin, 'user', user=self.admin)
        item = self.model('item').createItem(
            name='x.txt', creator=self.admin, folder=six.next(folders))
        file = self.model('file').createFile(
            creator=self.admin, item=item, name='x.txt',
            size=1, assetstore=assetstore, mimeType='text/plain')
        file['sha512'] = 'x'  # add this dummy value to simulate real file

        resp = self.request(path='/assetstore/{}'.format(assetstore['_id']),
                            method='DELETE', user=self.admin)
        self.assertStatus(resp, 400)
        self.assertEqual(resp.json['message'], 'You may not delete an '
                         'assetstore that contains files.')
        # Delete the offending file, we can now delete the assetstore
        self.model('file').remove(file)
        resp = self.request(path='/assetstore/{}'.format(assetstore['_id']),
                            method='DELETE', user=self.admin)
        self.assertStatusOk(resp)
        self.assertEqual(resp.json['message'],
                         'Deleted assetstore {}.'.format(assetstore['name']))

        resp = self.request(path='/assetstore', method='GET', user=self.admin)
        self.assertStatusOk(resp)
        self.assertEqual(1, len(resp.json))

        # Get the current assetstore.  It should now be the second store we
        # created
        current = self.model('assetstore').getCurrent()
        self.assertEqual(current['_id'], secondStore['_id'])

    def testGridFSAssetstoreAdapter(self):
        resp = self.request(path='/assetstore', method='GET', user=self.admin)
        self.assertStatusOk(resp)
        self.assertEqual(1, len(resp.json))
        oldAssetstore = resp.json[0]

        self.assertTrue(oldAssetstore['current'])
        self.assertEqual(oldAssetstore['name'], 'Test')
        # Clear any old DB data
        base.dropGridFSDatabase('girder_assetstore_create_test')
        params = {
            'name': 'New Name',
            'type': AssetstoreType.GRIDFS
        }
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertMissingParameter(resp, 'db')

        params['db'] = 'girder_assetstore_create_test'
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatusOk(resp)
        assetstore = resp.json
        self.assertEqual(assetstore['name'], 'New Name')
        self.assertFalse(assetstore['current'])

        # Set the new assetstore as current
        params = {
            'name': assetstore['name'],
            'db': assetstore['db'],
            'current': True
        }
        resp = self.request(path='/assetstore/{}'.format(assetstore['_id']),
                            method='PUT', user=self.admin, params=params)
        self.assertStatusOk(resp)
        assetstore = self.model('assetstore').load(resp.json['_id'])
        self.assertTrue(assetstore['current'])

        # The old assetstore should no longer be current
        oldAssetstore = self.model('assetstore').load(oldAssetstore['_id'])
        self.assertFalse(oldAssetstore['current'])

        # Test that we can create an assetstore with an alternate mongo host
        # and a replica set (but don't bother using an actual replica set)
        params = {
            'name': 'Replica Set Name',
            'type': AssetstoreType.GRIDFS,
            'db': 'girder_assetstore_rs_create_test',
            'mongohost': 'mongodb://127.0.0.1:27080,127.0.0.1:27081,'
                         '127.0.0.1:27082',
            'replicaset': 'replicaset'
        }
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatusOk(resp)
        rsassetstore = resp.json
        self.assertEqual(rsassetstore['name'], 'Replica Set Name')
        self.assertFalse(rsassetstore['current'])

        # Set the replica set assetstore as current
        params = {
            'name': rsassetstore['name'],
            'db': rsassetstore['db'],
            'mongohost': rsassetstore['mongohost'],
            'replicaset': rsassetstore['replicaset'],
            'current': True
        }
        resp = self.request(path='/assetstore/{}'.format(rsassetstore['_id']),
                            method='PUT', user=self.admin, params=params)
        self.assertStatusOk(resp)
        rsassetstore = self.model('assetstore').load(resp.json['_id'])
        self.assertTrue(rsassetstore['current'])

        # Neither of the old assetstores should  be current
        oldAssetstore = self.model('assetstore').load(oldAssetstore['_id'])
        self.assertFalse(oldAssetstore['current'])
        assetstore = self.model('assetstore').load(assetstore['_id'])
        self.assertFalse(assetstore['current'])

        # Getting the assetstores should succeed, even though we can't connect
        # to the replica set.
        resp = self.request(path='/assetstore', method='GET', user=self.admin)
        self.assertStatusOk(resp)

        # Change the replica set assetstore to use the default mongo instance,
        # which should be allowed, even though we won't be able to connect to
        # the database.
        params['mongohost'] = 'mongodb://127.0.0.1:27017'
        resp = self.request(path='/assetstore/{}'.format(rsassetstore['_id']),
                            method='PUT', user=self.admin, params=params)
        self.assertStatusOk(resp)
        resp = self.request(path='/assetstore', method='GET', user=self.admin)
        self.assertStatusOk(resp)

    @moto.mock_s3bucket_path
    def testS3AssetstoreAdapter(self):
        # Delete the default assetstore
        self.model('assetstore').remove(self.assetstore)
        s3Regex = r'^https://s3.amazonaws.com(:443)?/bucketname/foo/bar'

        params = {
            'name': 'S3 Assetstore',
            'type': AssetstoreType.S3,
            'bucket': '',
            'accessKeyId': 'someKey',
            'secret': 'someSecret',
            'prefix': '/foo/bar/'
        }

        # Validation should fail with empty bucket name
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatus(resp, 400)
        self.assertEqual(resp.json, {
            'type': 'validation',
            'field': 'bucket',
            'message': 'Bucket must not be empty.'
        })

        params['bucket'] = 'bucketname'
        # Validation should fail with a missing bucket
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatus(resp, 400)
        self.assertEqual(resp.json, {
            'type': 'validation',
            'field': 'bucket',
            'message': 'Unable to write into bucket "bucketname".'
        })

        # Validation should fail with a bogus service name
        params['service'] = 'ftp://nowhere'
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatus(resp, 400)
        del params['service']

        # Create a bucket (mocked using moto), so that we can create an
        # assetstore in it
        botoParams = makeBotoConnectParams(params['accessKeyId'],
                                           params['secret'])
        bucket = mock_s3.createBucket(botoParams, 'bucketname')

        # Create an assetstore
        resp = self.request(path='/assetstore', method='POST', user=self.admin,
                            params=params)
        self.assertStatusOk(resp)
        assetstore = self.model('assetstore').load(resp.json['_id'])

        # Set the assetstore to current.  This is really to test the edit
        # assetstore code.
        params['current'] = True
        resp = self.request(path='/assetstore/{}'.format(assetstore['_id']),
                            method='PUT', user=self.admin, params=params)
        self.assertStatusOk(resp)

        # Test init for a single-chunk upload
        folders = self.model('folder').childFolders(self.admin, 'user')
        parentFolder = six.next(folders)
        params = {
            'parentType': 'folder',
            'parentId': parentFolder['_id'],
            'name': 'My File.txt',
            'size': 1024,
            'mimeType': 'text/plain'
        }
        resp = self.request(path='/file', method='POST', user=self.admin,
                            params=params)
        self.assertStatusOk(resp)
        self.assertEqual(resp.json['received'], 0)
        self.assertEqual(resp.json['size'], 1024)
        self.assertEqual(resp.json['behavior'], 's3')

        singleChunkUpload = resp.json
        s3Info = singleChunkUpload['s3']
        self.assertEqual(s3Info['chunked'], False)
        self.assertEqual(type(s3Info['chunkLength']), int)
        self.assertEqual(s3Info['request']['method'], 'PUT')
        six.assertRegex(self, s3Info['request']['url'], s3Regex)
        self.assertEqual(s3Info['request']['headers']['x-amz-acl'], 'private')

        # Test resume of a single-chunk upload
        resp = self.request(path='/file/offset', method='GET', user=self.admin,
                            params={'uploadId': resp.json['_id']})
        self.assertStatusOk(resp)
        self.assertEqual(resp.json['method'], 'PUT')
        self.assertTrue('headers' in resp.json)
        six.assertRegex(self, resp.json['url'], s3Regex)

        # Test finalize for a single-chunk upload
        resp = self.request(path='/file/completion', method='POST',
                            user=self.admin,
                            params={'uploadId': singleChunkUpload['_id']})
        self.assertStatusOk(resp)
        self.assertFalse(resp.json['s3Verified'])
        self.assertEqual(resp.json['size'], 1024)
        self.assertEqual(resp.json['assetstoreId'], str(assetstore['_id']))
        self.assertTrue('s3Key' in resp.json)
        self.assertTrue(resp.json['relpath'].startswith('/bucketname/foo/bar/'))

        # Test init for a multi-chunk upload
        params['size'] = 1024 * 1024 * 1024 * 5
        resp = self.request(path='/file', method='POST', user=self.admin,
                            params=params)
        self.assertStatusOk(resp)

        multiChunkUpload = resp.json
        s3Info = multiChunkUpload['s3']
        self.assertEqual(s3Info['chunked'], True)
        self.assertEqual(type(s3Info['chunkLength']), int)
        self.assertEqual(s3Info['request']['method'], 'POST')
        six.assertRegex(self, s3Info['request']['url'], s3Regex)

        # Test uploading a chunk
        resp = self.request(path='/file/chunk', method='POST',
                            user=self.admin, params={
                                'uploadId': multiChunkUpload['_id'],
                                'offset': 0,
                                'chunk': json.dumps({
                                    'partNumber': 1,
                                    's3UploadId': 'abcd'
                                })
                            })
        self.assertStatusOk(resp)
        six.assertRegex(self, resp.json['s3']['request']['url'], s3Regex)
        self.assertEqual(resp.json['s3']['request']['method'], 'PUT')

        # We should not be able to call file/offset with multi-chunk upload
        resp = self.request(path='/file/offset', method='GET', user=self.admin,
                            params={'uploadId': multiChunkUpload['_id']})
        self.assertStatus(resp, 400)
        self.assertEqual(resp.json, {
            'type': 'validation',
            'message': 'You should not call requestOffset on a chunked '
                       'direct-to-S3 upload.'
        })

        # Test finalize for a multi-chunk upload
        resp = self.request(path='/file/completion', method='POST',
                            user=self.admin,
                            params={'uploadId': multiChunkUpload['_id']})
        largeFile = resp.json
        self.assertStatusOk(resp)
        six.assertRegex(self, resp.json['s3FinalizeRequest']['url'], s3Regex)
        self.assertEqual(resp.json['s3FinalizeRequest']['method'], 'POST')

        # Test init for an empty file (should be no-op)
        params['size'] = 0
        resp = self.request(path='/file', method='POST', user=self.admin,
                            params=params)
        emptyFile = resp.json
        self.assertStatusOk(resp)
        self.assertFalse('behavior' in resp.json)
        self.assertFalse('s3' in resp.json)

        # Test download for an empty file
        resp = self.request(path='/file/{}/download'.format(emptyFile['_id']),
                            user=self.admin, method='GET', isJson=False)
        self.assertStatusOk(resp)
        self.assertEqual(self.getBody(resp), '')
        self.assertEqual(resp.headers['Content-Length'], '0')
        self.assertEqual(resp.headers['Content-Disposition'],
                         'attachment; filename="My File.txt"')

        # Test download of a non-empty file
        resp = self.request(path='/file/{}/download'.format(largeFile['_id']),
                            user=self.admin, method='GET', isJson=False)
        self.assertStatus(resp, 303)
        six.assertRegex(self, resp.headers['Location'], s3Regex)

        # Test download as part of a streaming zip
        @httmock.all_requests
        def s3_pipe_mock(url, request):
            if(url.netloc.startswith('s3.amazonaws.com') and
                    url.scheme == 'https'):
                return 'dummy file contents'
            else:
                raise Exception('Unexpected url {}'.format(url))

        with httmock.HTTMock(s3_pipe_mock):
            resp = self.request(
                '/folder/{}/download'.format(parentFolder['_id']),
                method='GET', user=self.admin, isJson=False)
            self.assertStatusOk(resp)
            zip = zipfile.ZipFile(io.BytesIO(self.getBody(resp, text=False)),
                                  'r')
            self.assertTrue(zip.testzip() is None)

            extracted = zip.read('Public/My File.txt')
            self.assertEqual(extracted, b'dummy file contents')

        # Attempt to import item directly into user; should fail
        resp = self.request(
            '/assetstore/%s/import' % assetstore['_id'], method='POST', params={
                'importPath': '/foo/bar',
                'destinationType': 'user',
                'destinationId': self.admin['_id']
            }, user=self.admin)
        self.assertStatus(resp, 400)
        self.assertEqual(resp.json['message'],
                         'Keys cannot be imported directly underneath a user.')

        # Import existing data from S3
        resp = self.request('/folder', method='POST', params={
            'parentType': 'folder',
            'parentId': parentFolder['_id'],
            'name': 'import destinaton'
        }, user=self.admin)
        self.assertStatusOk(resp)
        importFolder = resp.json

        resp = self.request(
            '/assetstore/%s/import' % assetstore['_id'], method='POST', params={
                'importPath': '',
                'destinationType': 'folder',
                'destinationId': importFolder['_id'],
            }, user=self.admin)
        self.assertStatusOk(resp)

        # Data should now appear in the tree
        resp = self.request('/folder', user=self.admin, params={
            'parentId': importFolder['_id'],
            'parentType': 'folder'
        })
        self.assertStatusOk(resp)
        children = resp.json
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]['name'], 'foo')

        resp = self.request('/folder', user=self.admin, params={
            'parentId': children[0]['_id'],
            'parentType': 'folder'
        })
        self.assertStatusOk(resp)
        children = resp.json
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]['name'], 'bar')

        resp = self.request('/item', user=self.admin, params={
            'folderId': children[0]['_id']
        })
        self.assertStatusOk(resp)
        self.assertEqual(len(resp.json), 1)
        item = resp.json[0]
        self.assertEqual(item['name'], 'test')
        self.assertEqual(item['size'], 0)

        resp = self.request('/item/%s/files' % str(item['_id']),
                            user=self.admin)
        self.assertStatusOk(resp)
        self.assertEqual(len(resp.json), 1)
        file = resp.json[0]
        self.assertTrue(file['imported'])
        self.assertFalse('relpath' in file)
        self.assertEqual(file['size'], 0)
        self.assertEqual(file['assetstoreId'], str(assetstore['_id']))

        # Deleting an imported file should not delete it from S3
        self.assertTrue(bucket.get_key('/foo/bar/test') is not None)

        with mock.patch('girder.events.daemon.trigger') as daemon:
            resp = self.request('/item/%s' % str(item['_id']), method='DELETE',
                                user=self.admin)
            self.assertStatusOk(resp)
            self.assertEqual(len(daemon.mock_calls), 0)

        # Create the file key in the moto s3 store so that we can test that it
        # gets deleted.
        file = self.model('file').load(largeFile['_id'], user=self.admin)
        bucket.initiate_multipart_upload(file['s3Key'])
        key = bucket.new_key(file['s3Key'])
        key.set_contents_from_string("test")

        # Test delete for a non-empty file
        resp = self.request(path='/file/{}'.format(largeFile['_id']),
                            user=self.admin, method='DELETE')
        self.assertStatusOk(resp)

        # The file should be gone now
        resp = self.request(path='/file/{}/download'.format(largeFile['_id']),
                            user=self.admin, method='GET', isJson=False)
        self.assertStatus(resp, 400)
        # The actual delete may still be in the event queue, so we want to
        # check the S3 bucket directly.
        startTime = time.time()
        while True:
            if bucket.get_key(file['s3Key']) is None:
                break
            if time.time()-startTime > 15:
                break  # give up and fail
            time.sleep(0.1)
        self.assertIsNone(bucket.get_key(file['s3Key']))
