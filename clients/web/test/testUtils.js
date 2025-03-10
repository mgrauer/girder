/**
 * Contains utility functions used in the girder jasmine tests.
 */
var girderTest = girderTest || {};

window.alert = function (msg) {
    // alerts block phantomjs and will destroy us.
    console.log(msg);
};

// Timeout to wait for asynchronous actions
girderTest.TIMEOUT = 5000;

girderTest.createUser = function (login, email, firstName, lastName, password) {

    return function () {
        runs(function () {
            expect(girder.currentUser).toBe(null);
        });

        waitsFor(function () {
            return $('.g-register').length > 0;
        }, 'Girder app to render');

        runs(function () {
            $('.g-register').click();
        });

        girderTest.waitForDialog();
        waitsFor(function () {
            return $('input#g-email').length > 0;
        }, 'register dialog to appear');

        runs(function () {
            $('#g-login').val(login);
            $('#g-email').val(email);
            $('#g-firstName').val(firstName);
            $('#g-lastName').val(lastName);
            $('#g-password,#g-password2').val(password);
            $('#g-register-button').click();
        });

        waitsFor(function () {
            return $('.g-user-text a')[0].text === firstName + ' ' + lastName;
        }, 'user to be logged in');
        girderTest.waitForLoad();

        runs(function () {
            expect(girder.currentUser).not.toBe(null);
            expect(girder.currentUser.name()).toBe(firstName + ' ' + lastName);
            expect(girder.currentUser.get('login')).toBe(login);
        });
    };
};

girderTest.login = function (login, firstName, lastName, password) {

    return function () {

        runs(function () {
            expect(girder.currentUser).toBe(null);
        });

        waitsFor(function () {
            return $('.g-login').length > 0;
        }, 'Girder app to render');

        girderTest.waitForLoad();

        runs(function () {
            $('.g-login').click();
        });

        girderTest.waitForDialog();
        waitsFor(function () {
            return $('input#g-login').length > 0;
        }, 'register dialog to appear');

        runs(function () {
            $('#g-login').val(login);
            $('#g-password').val(password);
            $('#g-login-button').click();
        });

        waitsFor(function () {
            return $('.g-user-text a')[0].text === firstName + ' ' + lastName;
        }, 'user to be logged in');
        girderTest.waitForLoad();

        runs(function () {
            expect(girder.currentUser).not.toBe(null);
            expect(girder.currentUser.name()).toBe(firstName + ' ' + lastName);
            expect(girder.currentUser.get('login')).toBe(login);
        });
    };
};

girderTest.logout = function (desc) {

    return function () {
        runs(function () {
            expect(girder.currentUser).not.toBe(null);
        });

        waitsFor(function () {
            return $('.g-logout').length > 0;
        }, 'logout link to render');

        runs(function () {
            $('.g-logout').click();
        });

        waitsFor(function () {
            return girder.currentUser === null;
        }, 'user to be cleared');

        waitsFor(function () {
            return $('.g-login').length > 0;
        }, 'login link to appear');
        girderTest.waitForLoad(desc);
    };
};

girderTest.goToCurrentUserSettings = function () {

    return function () {
        runs(function () {
            expect(girder.currentUser).not.toBe(null);
        });

        waitsFor(function () {
            return $('.g-my-settings').length > 0;
        }, 'my account link to render');

        runs(function () {
            $('.g-my-settings').click();
        });

        waitsFor(function () {
            return $('input#g-email').length > 0;
        }, 'email input to appear');
        girderTest.waitForLoad();

        runs(function () {
            expect($('input#g-email').val()).toBe(girder.currentUser.get('email'));
            expect($('input#g-firstName').val()).toBe(girder.currentUser.get('firstName'));
            expect($('input#g-lastName').val()).toBe(girder.currentUser.get('lastName'));
        });
    };
};

// This assumes that you're logged into the system and on the create collection
// page.
girderTest.createCollection = function (collName, collDesc) {

    return function () {

        waitsFor(function () {
            return $('li.active .g-page-number').text() === 'Page 1' &&
                   $('.g-collection-create-button').is(':enabled');
        }, 'create collection button to appear');

        girderTest.waitForLoad();

        runs(function () {
            $('.g-collection-create-button').click();
        });

        waitsFor(function () {
            return Backbone.history.fragment.slice(-14) === '?dialog=create';
        }, 'url state to change indicating a creation dialog');

        girderTest.waitForDialog();
        waitsFor(function () {
            return $('input#g-name').length > 0 &&
                   $('.g-save-collection:visible').is(':enabled');
        }, 'create collection dialog to appear');

        runs(function () {
            $('#g-name').val(collName);
            $('#g-description').val(collDesc);
            $('.g-save-collection').click();
        });
        waitsFor(function () {
            return $('.g-collection-name').text() === collName &&
                   $('.g-collection-description').text() === collDesc;
        }, 'new collection page to load');
        girderTest.waitForLoad();
    };
};

// Go to groups page
girderTest.goToGroupsPage = function () {

    return function () {

        girderTest.waitForLoad();

        waitsFor(function () {
            return $("a.g-nav-link[g-target='groups']:visible").length > 0;
        }, 'groups nav link to appear');

        runs(function () {
            $("a.g-nav-link[g-target='groups']").click();
        });

        waitsFor(function () {
            return $(".g-group-search-form .g-search-field:visible").is(':enabled');
        }, 'navigate to groups page');
        girderTest.waitForLoad();
    };

};

// Go to users page
girderTest.goToUsersPage = function () {

    return function () {

        girderTest.waitForLoad();

        waitsFor(function () {
            return $("a.g-nav-link[g-target='users']:visible").length > 0;
        }, 'users nav link to appear');

        runs(function () {
            $("a.g-nav-link[g-target='users']").click();
        });

        waitsFor(function () {
            return $(".g-user-search-form .g-search-field:visible").is(':enabled');
        }, 'navigate to users page');
        girderTest.waitForLoad();
    };

};

// This assumes that you're logged into the system and on the groups page.
girderTest.createGroup = function (groupName, groupDesc, pub) {

    return function () {

        girderTest.waitForLoad();

        waitsFor(function () {
            return $('li.active .g-page-number').text() === 'Page 1' &&
                   $('.g-group-create-button:visible').is(':enabled');
        }, 'create group button to appear');

        runs(function () {
            $('.g-group-create-button').click();
        });

        girderTest.waitForDialog();
        waitsFor(function () {
            return $('#g-dialog-container').hasClass('in') &&
                   $('#g-access-public:visible').length > 0 &&
                   $('#g-name:visible').length > 0 &&
                   $('#g-description:visible').length > 0 &&
                   $('.g-save-group:visible').length > 0;
        }, 'create group dialog to appear');

        if (pub) {
            runs(function () {
                $('#g-access-public').click();
            });

            waitsFor(function () {
                return $('.g-save-group:visible').length > 0 &&
                       $('.radio.g-selected').text().match("Public").length > 0;
            }, 'access selection to be set to public');
        }

        runs(function () {
            $('#g-name').val(groupName);
            $('#g-description').val(groupDesc);
            $('.g-save-group').click();
        });

        waitsFor(function () {
            return $('.g-group-name').text() === groupName &&
                   $('.g-group-description').text() === groupDesc;
        }, 'new group page to load');
        girderTest.waitForLoad();
    };
};

/* This assumes that you're logged into the system and viewing a page that has
 * metadata editing options.
 */
girderTest.testMetadata = function () {
    /* Add metadata and check that the value is actually set for the item.
     * :param origKey: null to create a new metadata item.  Otherwise, edit the
     *                 metadata item with this key.
     * :param key: key text.
     * :param value: value text.  If this appears to be a JSON string, the
     *               metadata should be stored as a JSON object.
     * :param action: one of 'save', 'cance', or 'delete'.  'delete' can't be
     *                used with new items.  Default is 'save'.
     * :param errorMessage: if present, expect an information message with
     *                      regex.
     */
    function _editMetadata(origKey, key, value, action, errorMessage) {
        var expectedNum, elem;

        if (origKey === null) {
            waitsFor(function () {
                return $('.g-widget-metadata-add-button:visible').length === 1;
            }, 'the add metadata button to appear');
            runs(function () {
                expectedNum = $(".g-widget-metadata-row").length;
                $('.g-widget-metadata-add-button:visible').click();
            });
        } else {
            runs(function () {
                elem = $('.g-widget-metadata-key:contains("' + origKey + '")').closest('.g-widget-metadata-row');
                expect(elem.length).toBe(1);
                expect($('.g-widget-metadata-edit-button', elem).length).toBe(1);
                expectedNum = $(".g-widget-metadata-row").length;
                $('.g-widget-metadata-edit-button', elem).click();
            });
        }
        waitsFor(function () {
            return $('input.g-widget-metadata-key-input').length === 1 &&
                   $('textarea.g-widget-metadata-value-input').length === 1;
        }, 'the add metadata input fields to appear');
        runs(function () {
            if (!elem) {
                elem = $('input.g-widget-metadata-key-input').closest('.g-widget-metadata-row');
            }
            if (key !== null) {
                $('input.g-widget-metadata-key-input', elem).val(key);
            } else {
                key = $('input.g-widget-metadata-key-input', elem).val();
            }
            if (value !== null) {
                $('textarea.g-widget-metadata-value-input', elem).val(value);
            } else {
                value = $('textarea.g-widget-metadata-value-input', elem).val();
            }
        });
        if (errorMessage) {
            runs(function () {
                $('.g-widget-metadata-save-button').click();
            });
            waitsFor(function () {
                return $('.alert').text().match(errorMessage);
            }, 'alert with "' + errorMessage + '" to appear');
        }
        switch (action)
        {
            case 'cancel':
                runs(function () {
                    $('.g-widget-metadata-cancel-button').click();
                });
                break;
            case 'delete':
                runs(function () {
                    $('.g-widget-metadata-delete-button').click();
                });
                girderTest.waitForDialog();
                waitsFor(function () {
                    return $('#g-confirm-button:visible').length > 0;
                }, 'delete confirmation to appear');
                runs(function () {
                    $('#g-confirm-button').click();
                    expectedNum -= 1;
                });
                girderTest.waitForLoad();
                break;
            default:
                action = 'save';
                runs(function () {
                    $('.g-widget-metadata-save-button').click();
                    if (origKey === null) {
                        expectedNum += 1;
                    }
                });
                break;
        }
        waitsFor(function () {
            return $('input.g-widget-metadata-key-input').length === 0 &&
                   $('textarea.g-widget-metadata-value-input').length === 0;
        }, 'edit fields to disappear');
        waitsFor(function () {
            return $(".g-widget-metadata-row").length == expectedNum;
        }, 'the correct number of items to be listed');
        runs(function () {
            expect($(".g-widget-metadata-row").length).toBe(expectedNum);
            if (action === 'save') {
                expect(elem.text()).toBe(key + value);
            }
        });
    }

    return function () {
        _editMetadata(null, 'simple_key', 'simple_value');
        _editMetadata(null, 'simple_key', 'duplicate_key_should_fail', 'cancel', /.*simple_key is already a metadata key/);
        _editMetadata(null, '', 'no_key', 'cancel', /.*A key is required for all metadata/);
        _editMetadata(null, 'cancel_me', 'this will be cancelled', 'cancel');
        _editMetadata(null, 'long_key', 'long_value' + new Array(2048).join('-'));
        _editMetadata(null, 'json_key', JSON.stringify({sample_json: 'value'}));
        _editMetadata(null, 'unicode_key\u00A9\uD834\uDF06', 'unicode_value\u00A9\uD834\uDF06');
        _editMetadata('simple_key', null, 'new_value', 'cancel');
        _editMetadata('long_key', 'json_key', null, 'cancel', /.*json_key is already a metadata key/);
        _editMetadata('simple_key', null, 'new_value');
        _editMetadata('simple_key', null, null, 'delete');
        _editMetadata('json_key', 'json_rename', null);
    };
};

/**
 * Wait for all loading blocks to be fully loaded.  Also, remove the dialog
 * backdrop, since it isn't properly removed on phantomJS.  This should not be
 * called on dialogs.
 */
girderTest.waitForLoad = function (desc) {
    desc = desc ? ' (' + desc + ')' : '';
    waitsFor(function () {
        return $('#g-dialog-container:visible').length === 0;
    }, 'for the dialog container to be hidden' + desc);
    /* It is faster to wait to make sure a dialog is being hidden than to wait
     * for it to be fully gone.  It is probably more reliable, too.  This had
     * been:
    waitsFor(function () {
        return $('.modal-backdrop').length === 0;
    }, 'for the modal backdrop to go away'+desc);
    */
    waitsFor(function () {
        if ($('.modal').data('bs.modal') === undefined) {
            return true;
        }
        if ($('.modal').data('bs.modal').isShown !== false &&
            $('.modal').data('bs.modal').isShown !== null) {
            return false;
        }
        return !$('.modal').data('bs.modal').$backdrop;
    }, 'for any modal dialog to be hidden' + desc);
    waitsFor(function () {
        return girder.numberOutstandingRestRequests() === 0;
    }, 'rest requests to finish' + desc);
    waitsFor(function () {
        return $('.g-loading-block').length === 0;
    }, 'all blocks to finish loading' + desc);
};

/**
 * Wait for a dialog to be visible.
 */
girderTest.waitForDialog = function (desc) {
    desc = desc ? ' (' + desc + ')' : '';
    /* It is faster to wait until the dialog is officially shown than to wait
     * for the backdrop.  This had been:
    waitsFor(function() {
        return $('#g-dialog-container:visible').length > 0 &&
               $('.modal-backdrop:visible').length > 0;
    }, 'a dialog to fully render'+desc);
     */
    waitsFor(function () {
        return $('.modal').data('bs.modal') &&
               $('.modal').data('bs.modal').isShown === true &&
               $('#g-dialog-container:visible').length > 0;
    }, 'a dialog to fully render' + desc);
    waitsFor(function () {
        return girder.numberOutstandingRestRequests() === 0;
    }, 'dialog rest requests to finish' + desc);
};

/**
 * Import a javascript file and ask to register it with the blanket coverage
 * tests.
 */
girderTest.addCoveredScript = function (url) {
    if (window.blanket) {
        blanket.utils.cache[url] = {};
        blanket.utils.attachScript({url:url}, function (content) {
            blanket.instrument({inputFile: content, inputFileName: url},
                function (instrumented) {
                    blanket.utils.cache[url].loaded = true;
                    blanket.utils.blanketEval(instrumented);
                    blanket.requiringFile(url, true);
                });
        });
    } else {
        $('<script/>', {src: url}).appendTo('head');
    }
};

/**
 * Import a list of covered scripts. Order will be respected.
 */
girderTest.addCoveredScripts = function (scripts) {
    _.each(scripts, girderTest.addCoveredScript);
};

/**
 * Import a CSS file into the runtime context.
 */
girderTest.importStylesheet = function (css) {
    $('<link/>', {
        rel: 'stylesheet',
        type: 'text/css',
        href: css
    }).appendTo('head');
};

/**
 * For the current folder, check if it is public or private and take an action.
 * :param current: either 'public' or 'private': expect this value to match.
 * :param action: if 'public' or 'private', switch to that setting.
  */
girderTest.folderAccessControl = function (current, action, recurse) {
    waitsFor(function () {
        return $('.g-folder-access-button:visible').length === 1;
    }, 'folder access button to be available');

    runs(function () {
        $('.g-folder-access-button').click();
    });
    girderTest.waitForDialog();

    waitsFor(function () {
        return $('#g-dialog-container').hasClass('in') &&
               $('#g-access-private:visible').is(':enabled');
    }, 'dialog and private access radio button to appear');

    runs(function () {
        expect($('#g-access-' + current + ':checked').length).toBe(1);
        $('#g-access-' + action).click();

        if (recurse) {
            $('#g-apply-recursive').click();
        } else {
            $('#g-apply-nonrecursive').click();
        }
    });

    waitsFor(function () {
        switch (action) {
            case 'private':
                if (!$('.radio.g-selected').text().match("Private").length) {
                    return false;
                }
                break;
            case 'public':
                if (!$('.radio.g-selected').text().match("Public").length) {
                    return false;
                }
                break;
        }
        return $('.g-save-access-list:visible').is(':enabled');
    }, 'access save button to appear');

    runs(function () {
        $('.g-save-access-list').click();
    });

    girderTest.waitForLoad();

    waitsFor(function () {
        return !$('#g-dialog-container').hasClass('in');
    }, 'access dialog to be hidden');
};

/**
 * Use this to upload a binary file into the currently visible folder. We can't
 * upload binary files correctly in phantom, so we rely on a special test-only
 * endpoint to do the work for us.
 *
 * @param path should be specified relative to the root of the repository.
 */
girderTest.binaryUpload = function (path) {
    var file;
    var oldLen;

    runs(function () {
        var folderId = Backbone.history.fragment.split('/').pop();
        oldLen = $('.g-item-list-entry').length;

        girder.restRequest({
            path: 'webclienttest/file',
            type: 'POST',
            data: {
                path: path,
                folderId: folderId
            }
        }).done(function (resp) {
            file = resp;
        }).error(function (resp) {
            console.log('Could not complete simulated upload of ' + path + ' to ' + folderId);
            console.log(resp.responseJSON.message);
        });
    });

    waitsFor(function () {
        return !!file;
    }, 'simulated binary upload to finish');

    runs(function () {
        // Reload the current view
        var old = Backbone.history.fragment;
        Backbone.history.fragment = null;
        girder.router.navigate(old, {trigger: true});
    });

    waitsFor(function () {
        return $('.g-item-list-entry').length === oldLen + 1;
    }, 'newly uploaded item to appear after refresh');
};

/* Test going to a particular route, waiting for the dialog or page to load
 *  fully, and then testing that we have what we expect.
 * Enter: route: the hash url fragment to go to.
 *        hasDialog: true if we should wait for a dialog to appear.
 *        testFunc: a function with an expect call to validate the route.  If
 *                  this is not specified, just navigate to the specified
 *                  route.
 */
girderTest.testRoute = function (route, hasDialog, testFunc) {
    runs(function () {
        if (route.indexOf('#') === 0) {
            route = route.substr(1);
        }
        window.location.hash = route;
    });
    /* We need to let the window have a chance to reload, so we just release
     * our time slice. */
    waits(1);
    if (hasDialog) {
        girderTest.waitForDialog('route: ' + route);
    } else {
        girderTest.waitForLoad('route: ' + route);
    }
    if (testFunc) {
        waitsFor(testFunc, 'route: ' + route);
        runs(function () {
            expect(testFunc()).toBe(true);
        });
    }
};

/* Determine a value used to keep tests using different files.
 * @returns suffix: the suffix used in callPhantom actions.
 */
girderTest.getCallbackSuffix = function () {
    girderTest._uploadSuffix = '';
    var hostport = window.location.host.match(':([0-9]+)');
    if (hostport && hostport.length === 2) {
        girderTest._uploadSuffix = hostport[1];
    }
    return girderTest._uploadSuffix;
};

/* Upload tests require that we modify how xmlhttp requests are handled.  Check
 * that this has been done (but only do it once).
 */
function _prepareTestUpload() {
    if (girderTest._preparedTestUpload) {
        return;
    }
    girderTest._uploadData = null;
    /* used for resume testing */
    girderTest._uploadDataExtra = 0;
    girderTest.getCallbackSuffix();

    (function (impl) {
        FormData.prototype.append = function (name, value, filename) {
            this.vals = this.vals || {};
            if (filename) {
                this.vals[name + '_filename'] = value;
            }
            this.vals[name] = value;
            impl.call(this, name, value, filename);
        };
    } (FormData.prototype.append));

    (function (impl) {
        XMLHttpRequest.prototype.send = function (data) {
            if (data && data instanceof FormData) {
                var newdata = new FormData();
                newdata.append('offset', data.vals.offset);
                newdata.append('uploadId', data.vals.uploadId);
                var len = data.vals.chunk.size;
                if (girderTest._uploadData.length &&
                        girderTest._uploadData.length == len &&
                        !girderTest._uploadDataExtra) {
                    newdata.append('chunk', girderTest._uploadData);
                } else {
                    newdata.append('chunk', new Array(
                        len + 1 + girderTest._uploadDataExtra).join('-'));
                }
                data = newdata;
            } else if (data && data instanceof Blob) {
                if (girderTest._uploadDataExtra) {
                    /* Our mock S3 server will take extra data, so break it
                     * by adding a faulty copy header.  This will throw an
                     * error so we can test resumes. */
                    this.setRequestHeader('x-amz-copy-source', 'bad_value');
                }
                if (girderTest._uploadData.length &&
                        girderTest._uploadData.length == data.size &&
                        !girderTest._uploadDataExtra) {
                    data = girderTest._uploadData;
                } else {
                    data = new Array(
                        data.size + 1 + girderTest._uploadDataExtra).join('-');
                }
            }
            impl.call(this, data);
        };
    } (XMLHttpRequest.prototype.send));

    girderTest._preparedTestUpload = true;
}

girderTest.sendFile = function (uploadItem) {
    // Incantation that causes the phantom environment to send us a File.
    $('#g-files').parent().removeClass('hide');
    var params = {
        action: 'uploadFile',
        selector: '#g-files',
        suffix: girderTest._uploadSuffix
    };
    if (uploadItem === parseInt(uploadItem)) {
        params.size = uploadItem;
    } else {
        params.path = uploadItem;
    }
    girderTest._uploadData = window.callPhantom(params);
};

/* Upload a file and make sure it lands properly.
 * @param uploadItem: either the path to the file to upload or an integer to
 *                    create and upload a temporary file of that size.
 * @param needResume: if true, upload a partial file so that we are asked if we
 *                    want to resume, then resume.  If 'abort', then abort the
 *                    upload instead of resuming it.
 * @param error: if present and the needResume is set, then we expect the
 *               upload to fail with an error that includes this string.
 */
girderTest.testUpload = function (uploadItem, needResume, error) {
    var orig_len;

    _prepareTestUpload();

    waitsFor(function () {
        return $('.g-upload-here-button').length > 0;
    }, 'the upload here button to appear');

    runs(function () {
        orig_len = $('.g-item-list-entry').length;
        $('.g-upload-here-button').click();
    });

    waitsFor(function () {
        return $('.g-drop-zone:visible').length > 0 &&
               $('.modal-dialog:visible').length > 0;
    }, 'the upload dialog to appear');

    runs(function () {
        if (needResume) {
            girderTest._uploadDataExtra = 1024 * 20;
        } else {
            girderTest._uploadDataExtra = 0;
        }

        girderTest.sendFile(uploadItem);
    });

    waitsFor(function () {
        return $('.g-overall-progress-message i.icon-ok').length > 0;
    }, 'the file to be received');

    runs(function () {
        $('#g-files').parent().addClass('hide');
        $('.g-start-upload').click();
    });

    if (needResume) {
        waitsFor(function () {
            return $('.g-resume-upload:visible').length > 0 ||
                   $('.g-restart-upload:visible').length > 0;
        }, 'the resume link to appear');
        runs(function () {
            if (error) {
                expect($('.g-upload-error-message').text().indexOf(
                    error) >= 0).toBe(true);
            }
            girderTest._uploadDataExtra = 0;

            if (needResume == 'abort') {
                $('.btn-default').click();
                orig_len -= 1;
            } else {
                $('.g-resume-upload').click();
            }
        });
    }

    waitsFor(function () {
        return $('.modal-content:visible').length === 0 &&
               $('.g-item-list-entry').length === orig_len + 1;
    }, 'the upload to finish');
    girderTest.waitForLoad();

    window.callPhantom(
        {action: 'uploadCleanup',
        suffix: girderTest._uploadSuffix});
};

/* Wait for a dialog to be present with a confirm button, then select the
 * confirm button and wait for teh dialog to be hidden.
 */
girderTest.confirmDialog = function () {
    girderTest.waitForDialog('wait for confirmation');
    waitsFor(function () {
        return $('#g-confirm-button:visible').length > 0;
    }, 'confirmation to appear');
    runs(function () {
        $('#g-confirm-button').click();
    });
    girderTest.waitForLoad();
};

girderTest.shimBlobBuilder = function () {
    var oldPrototype = window.Blob.prototype;
    window.BlobBuilder = window.BlobBuilder || window.WebKitBlobBuilder;
    window.Blob = function (data) {
        var builder = new window.BlobBuilder();
        _.each(data, function (d) {
            builder.append(d);
        });
        return builder.getBlob();
    };
    window.Blob.prototype = oldPrototype;
};

/*
 * Loads a particular fragment as anonymous and checks whether the login dialog
 * appears.  Assumes you are logged out, or else you should pass logoutFirst=true.
 * If you would like the system to log back in at the end of this function,
 * pass a loginFunction to be called.
 */
girderTest.anonymousLoadPage = function (logoutFirst, fragment, hasLoginDialog, loginFunction) {
    /*
     * :param logoutFirst: boolean, whether this function should log out the current user
     *                     before loading the fragment.
     * :param fragment: URL fragment to load.
     * :param hasLoginDialog: boolean, whether the page loaded at the fragment's route should
     *                        display a login dialog.
     * :param loginFunction: function, if passed, the loginFunction will be called at the end of
     *                       this function to log the user back in.
     */
    if (logoutFirst) {
        girderTest.logout()();
    }
    girderTest.testRoute(fragment, hasLoginDialog);
    if (hasLoginDialog) {
        waitsFor(function () {
            return $('input#g-login').length > 0;
        }, 'login dialog to appear');
    }
    girderTest.testRoute('', false);
    if (loginFunction) {
        loginFunction();
    }
};
