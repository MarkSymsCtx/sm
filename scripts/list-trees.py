#!/usr/bin/python

#
# Copyright (C) Citrix Systems Inc.
#
# This program is free software; you can redistribute it and/or modify 
# it under the terms of the GNU Lesser General Public License as published 
# by the Free Software Foundation; version 2.1 only.
#
# This program is distributed in the hope that it will be useful, 
# but WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the 
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#

import importlib
import os
import sys

TREE_INDENT = 4

MODULES = {}

GIGA = 1024 * 1024 * 1024


class VDI(object):

    def __init__(self, vdiInfo, size_extract):
        self.children = []
        self.parent = None
        self.info = vdiInfo
        self.size_extract= size_extract

    def size_string(self, size):
        if not size:
            return '?'

        return '{:.2f}G'.format(size)

    def __repr__(self):
        phys, virt = 0, 0
        if self.size_extract:
            phys, virt = self.size_extract(self.info)

        return '{}({}/{})'.format(
            self.info.uuid,
            self.size_string(virt),
            self.size_string(phys))


def build_trees(vdis, size_extract=None):
    """
    Walk the VDIs and create trees
    """
    vdi_trees = []

    working_vdis = {k:VDI(v, size_extract) for (k, v) in vdis.items()}

    for vdi in working_vdis.values():
        if vdi.info.parentUuid:
            parent = working_vdis.get(vdi.info.parentUuid)
            if not parent:
                raise Exception('Missing parent vdi {}'.format(vdi.info.parentUuid))


            vdi.parent = parent
            parent.children.append(vdi)
        else:
            vdi_trees.append(vdi)

    return vdi_trees


def get_tree_str(tree, indent = TREE_INDENT):
    """
    Convert the tree to an indented string
    """
    tree_str = '{}{}\n'.format(" " * indent, tree)
    for child in tree.children:
        tree_str += get_tree_str(child, indent + TREE_INDENT)

    return tree_str


def list_tree(vdis, size_extract=None):
    """
    Print the indented tree of VMs
    """
    trees = build_trees(vdis, size_extract)

    print 'Displaying {} tree(s) for sr'.format(len(trees))

    tree_str = ''
    for tree in trees:
        tree_str += get_tree_str(tree)

    print tree_str


def to_giga(size):
    return float(size) / GIGA


def lvm_lister(sr):
    """
    List VHDs on an LVM SR
    """
    vgName = "%s%s" % (MODULES['lvhdutil'].VG_PREFIX, sr['uuid'])
    lvmCache = MODULES['lvmcache'].LVMCache(vgName)
    lvmCache.refresh()
    vdis = MODULES['lvhdutil'].getVDIInfo(lvmCache)

    def extract_sizes(vdi):
        return (to_giga(vdi.sizeLV), to_giga(vdi.sizeVirt))

    list_tree(vdis, size_extract=extract_sizes)


def extract_uuid(path):
    """
    Extract VHD uid from filename
    """
    path = os.path.basename(path.strip())
    if not (path.endswith(MODULES['vhdutil'].FILE_EXTN_VHD) or \
            path.endswith(MODULES['vhdutil'].FILE_EXTN_RAW)):
        return None
    uuid = path.replace(MODULES['vhdutil'].FILE_EXTN_VHD, "").replace( \
                MODULES['vhdutil'].FILE_EXTN_RAW, "")
    return uuid


def file_lister(sr):
    """
    List VHDs on File SR
    """
    sr_path = '/var/run/sr-mount/{}'.format(sr['uuid'])
    pattern = os.path.join(sr_path, "*.vhd")
    vhds = MODULES['vhdutil'].getAllVHDs(pattern, extract_uuid)

    def extract_sizes(vdi):
        return (to_giga(vdi.sizePhys), to_giga(vdi.sizeVirt))

    list_tree(vhds, size_extract=extract_sizes)


TREE_LISTERS = {
    'lvmoiscsi': lvm_lister,
    'lvmohba': lvm_lister,
    'lvmofcoe': lvm_lister,
    'lvm': lvm_lister,
    'nfs': file_lister,
    'smb': file_lister,
    'ext': file_lister
}


def filter_vhd_srs(srs):
    """
    Reduce the input list to only those SRs with VHDs
    """
    return {k:v for (k, v) in srs.items() if v['type'] in TREE_LISTERS}


def list_sr_trees():
    """
    List the VHD trees in all the SRs on the host
    """
    try:
        session = MODULES['sm_util'].get_localAPI_session()
    except:
        print "Unable to open local XAPI session"
        sys.exit(-1)

    srs = session.xenapi.SR.get_all_records()

    for vhd_sr in filter_vhd_srs(srs):
        sr = srs[vhd_sr]
        print '{}({}) - {}'.format(sr['name_label'], sr['uuid'], sr['type'])
        TREE_LISTERS[sr['type']](sr)


def import_other_modules():
    """
    Import the forign modules that aren't on the python path
    """
    sys.path.append('/opt/xensource/sm/')
    MODULES['sm_util'] = importlib.import_module('util')
    MODULES['xs_errors'] = importlib.import_module('xs_errors')
    MODULES['lvhdutil'] = importlib.import_module('lvhdutil')
    MODULES['lvmcache'] = importlib.import_module('lvmcache')
    MODULES['vhdutil'] = importlib.import_module('vhdutil')


if __name__ == "__main__":
    import_other_modules()
    list_sr_trees()
