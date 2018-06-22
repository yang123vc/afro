""" parse file system

Parse:
1. Parse container superblock.
    3. Parse OMAP.
    4. Iterate over volumes.
        5. Get volume superblocks from OMAP.
            6. Parse volume superblock.
                7. Parse OMAP.
                8. Go to root directory.
                    9. Parse Root directory. Parse required entries.
    10. Go to previous container superblock. Recurse 1.
"""
import logging

from kaitaistruct import KaitaiStream, BytesIO

from . import libapfs, block

LOGGER = logging.getLogger(__name__)

def add_file_entries(file_entries, new_file_entries, xid_override, volume_override=None):
    for xid in new_file_entries:
        file_entries.setdefault(xid_override, dict())
        for volume in new_file_entries[xid]:
            volume_override = volume_override or volume
            file_entries[xid_override].setdefault(volume_override, list())
            file_entries[xid_override][volume_override] += new_file_entries[xid][volume]
    return file_entries

def parse_node(node, apfs):
    # 'unknown' is the default volume name
    # node_type 1 contains only pointer records
    if node.body.node_type == 1:
        return {node.hdr.xid: {'unknown': []}}
    return {node.hdr.xid: {'unknown': node.body.entries}}

def parse_apsb(apsb, apfs):
    file_entries = dict()

    for omap_entry in libapfs.get_apsb_objects(apsb):
        # get root directory
        root_node = omap_entry.val.obj_id.target
        new_file_entries = parse_node(root_node, apfs)
        file_entries = add_file_entries(file_entries, new_file_entries, apsb.hdr.xid, apsb.body.volname)

    return file_entries

def parse_nxsb(nxsb, apfs):
    file_entries = dict()

    for fs_entry in libapfs.get_nxsb_objects(nxsb):
        # get volume superblock
        apsb = fs_entry.val.obj_id.target
        new_file_entries = parse_apsb(apsb, apfs)
        file_entries = add_file_entries(file_entries, new_file_entries, nxsb.hdr.xid)

    return file_entries

def parse(image_io, image_name):
    """ parse image and print files """

    # get file entries
    apfs = libapfs.Apfs(KaitaiStream(image_io))

    # get from container superblock
    nxsb = apfs.block0
    block_size = nxsb.body.block_size
    file_entries = parse_nxsb(nxsb, apfs)
    prev_nxsb = nxsb.body.xp_desc_base + nxsb.body.xp_desc_index + 1
    count = nxsb.body.xp_desc_index_len

    # get from older container superblocks
    for x in range(count - 1):
        data = block.get_block(prev_nxsb, block_size, image_io)
        nxsb = apfs.Obj(KaitaiStream(BytesIO(data)), apfs, apfs)
        try:
            file_entries = {**file_entries, **parse_nxsb(nxsb, apfs)}
            prev_nxsb = nxsb.body.xp_desc_base + nxsb.body.xp_desc_index + 1
        except:
            break

    return file_entries