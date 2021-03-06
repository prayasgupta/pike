#
# Copyright (c) 2013, EMC Corporation
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Module Name:
#
#        lease.py
#
# Abstract:
#
#        Lease tests
#
# Authors: Brian Koropoff (brian.koropoff@emc.com)
#

import pike.model
import pike.smb2
import pike.test
import random
import array

@pike.test.RequireDialect(0x210)
@pike.test.RequireCapabilities(pike.smb2.SMB2_GLOBAL_CAP_LEASING)
class LeaseTest(pike.test.PikeTest):
    def __init__(self, *args, **kwargs):
        super(LeaseTest, self).__init__(*args, **kwargs)
        self.share_all = pike.smb2.FILE_SHARE_READ | pike.smb2.FILE_SHARE_WRITE | pike.smb2.FILE_SHARE_DELETE
        self.lease1 = array.array('B',map(random.randint, [0]*16, [255]*16))
        self.lease2 = array.array('B',map(random.randint, [0]*16, [255]*16))
        self.r = pike.smb2.SMB2_LEASE_READ_CACHING
        self.rw = self.r | pike.smb2.SMB2_LEASE_WRITE_CACHING
        self.rh = self.r | pike.smb2.SMB2_LEASE_HANDLE_CACHING
        self.rwh = self.rw | self.rh

    # Upgrade lease from RW to RWH, then break it to R
    def test_lease_upgrade_break(self):
        chan, tree = self.tree_connect()
        
        # Request rw lease
        handle1 = chan.create(tree,
                              'lease.txt',
                              share=self.share_all,
                              oplock_level=pike.smb2.SMB2_OPLOCK_LEVEL_LEASE,
                              lease_key = self.lease1,
                              lease_state = self.rw).result()
    
        self.assertEqual(handle1.lease.lease_state, self.rw)
        
        handle2 = chan.create(tree,
                              'lease.txt',
                              share=self.share_all,
                              oplock_level=pike.smb2.SMB2_OPLOCK_LEVEL_LEASE,
                              lease_key = self.lease1,
                              lease_state = self.rwh).result()

        self.assertIs(handle2.lease, handle1.lease)
        self.assertEqual(handle2.lease.lease_state, self.rwh)

        # On break, voluntarily give up handle caching
        handle2.lease.on_break(lambda state: state & ~pike.smb2.SMB2_LEASE_HANDLE_CACHING)
   
        # Break our lease
        handle3 = chan.create(tree,
                              'lease.txt',
                              share=self.share_all,
                              oplock_level=pike.smb2.SMB2_OPLOCK_LEVEL_LEASE,
                              lease_key = self.lease2,
                              lease_state = self.rwh).result()

        # First lease should have broken to r
        self.assertEqual(handle2.lease.lease_state, self.r)
        # Should be granted rh on second lease
        self.assertEqual(handle3.lease.lease_state, self.rh)

        chan.close(handle1)
        chan.close(handle2)
        chan.close(handle3)

    # Close handle associated with lease while a break is in progress
    def test_lease_break_close_ack(self):
        chan, tree = self.tree_connect()
        # Request rw lease
        handle1 = chan.create(tree,
                              'lease.txt',
                              share=self.share_all,
                              oplock_level=pike.smb2.SMB2_OPLOCK_LEVEL_LEASE,
                              lease_key = self.lease1,
                              lease_state = self.rw).result()
        
        # Upgrade to rwh
        handle2 = chan.create(tree,
                              'lease.txt',
                              share=self.share_all,
                              oplock_level=pike.smb2.SMB2_OPLOCK_LEVEL_LEASE,
                              lease_key = self.lease1,
                              lease_state = self.rwh).result()
        
        # Break our lease
        handle3_future = chan.create(tree,
                                     'lease.txt',
                                     share=self.share_all,
                                     oplock_level=pike.smb2.SMB2_OPLOCK_LEVEL_LEASE,
                                     lease_key = self.lease2,
                                     lease_state = self.rwh)
        
        # Wait for break
        handle1.lease.future.wait()
        
        # Close second handle
        chan.close(handle2)
        
        # Now ack break
        handle1.lease.on_break(lambda state: state)
        
        # Wait for handle3
        handle3 = handle3_future.result()
        
        chan.close(handle1)
        chan.close(handle3)
