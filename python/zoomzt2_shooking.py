#!/usr/bin/python
#
# Script decode/encode ZT2 file from Zoom F/W
# (c) Simon Wood, 11 July 2019
#

from construct import *
import re
# some of the files have traiing ,
# json5 accepts this, but is slower than json.
import json5
import math

#--------------------------------------------------
# Define ZT2/ZD2 file format using Construct (v2.10)
# requires:
# https://github.com/construct/construct

Header = Struct(
    "a" / Const(b"\x3e\x3e\x3e\x00"),
    "b" / Padding(22),
    "name" / PaddedString(12, "ascii"),
    "c" / Padding(6),
    "d" / Const(b"\x01"),
    "e" / Padding(7),
    "f" / Const(b"\x3c\x3c\x3c\x00"),
    "g" / Padding(22),
)

Effect = Struct(
    "effect" / PaddedString(12, "ascii"),
    Const(b"\x00"),
    "version" / PaddedString(4, "ascii"),
    Const(b"\x00"),
    "installed" / Default(Byte, 1),     # "Guitar Lab additional effects" = 0
    "id" / Int32ul,
    "group" / Computed((this.id & 0xFF000000) >> 24),
    Check(this.group == this._.group),
    Const(b"\x00\x00\x00"),
)

Group = Struct(
    Const(b"\x3e\x3e\x3e\x00"),
    "group" / Byte,
    "groupname" / Enum(Computed(this.group),
        DYNAMICS = 1,
    FILTER = 2,
    DRIVE = 3,
    AMP = 4,
    CABINET = 5,
    MODULATION = 6,
    SFX = 7,
    DELAY = 8,
    REVERB = 9,
    PEDAL = 11,
    ACOUSTIC = 29,
    ),
    Padding(21),
    "effects" / GreedyRange(Effect),
    Const(b"\x3c\x3c\x3c\x00"),
    "group_end" / Rebuild(Byte, this.group),
    Check(this.group_end == this.group),
    Padding(21),
)

ZT2 = Padded(8502, Sequence(
    "header" / Header,
    "groups" / GreedyRange(Group),
))

ZD2 = Struct(
    Const(b"\x5a\x44\x4c\x46\x78"),
    Padding(84),
    "version" / PaddedString(4, "ascii"),
    Const(b"\x00\x00"),
    "group" / Byte,
    "groupname" / Enum(Computed(this.group),
        DYNAMICS = 1,
    FILTER = 2,
    DRIVE = 3,
    AMP = 4,
    CABINET = 5,
    MODULATION = 6,
    SFX = 7,
    DELAY = 8,
    REVERB = 9,
    PEDAL = 11,
    ACOUSTIC = 29,
    ),
    "id" / Int32ul,
    "name" / CString("ascii"),
)

PTCF = Struct(
    Const(b"PTCF"),
    Padding(8),
    "effects" / Int32ul,
    Padding(10),
    "name" / PaddedString(10, "ascii"),
    "id1" / Int32ul,
    "id2" / Int32ul,
    "id3" / Int32ul,
    "id4" / Int32ul,
    "id5" / Int32ul,
)

TXJ1 = Struct(
    Const(b"TXJ1"),
    "length" / Int32ul,
    Padding(this.length),
)

TXE1 = Struct(
    Const(b"TXE1"),
    "length" / Int32ul,
    "name" / PaddedString(this.length, "ascii"),
)

EDTB2 = Struct( # Working with a Byte-reversed copy of data
    Padding(9),
    "control" / Bitwise(Struct(
        Padding(6),
        "param8" / BitsInteger(8),
        "param7" / BitsInteger(8),
        "param6" / BitsInteger(8),
        "param5" / BitsInteger(12),
        "param4" / BitsInteger(12),
        "param3" / BitsInteger(12),
        "param2" / BitsInteger(12),
        "param1" / BitsInteger(12),
        "unknown" / Bit, # always '0', so far
        "id" / BitsInteger(28),
        "enabled" / Flag,
    )),
)

EDTB1 = Struct(
    "dump" / Peek(HexDump(Bytes(24))),
    "autorev" / ByteSwapped(Bytes(24)),
    "reversed" / RestreamData(this.autorev, EDTB2), # this does not allow re-build of data :-(
)

EDTB = Struct(
    Const(b"EDTB"),
    "length" / Int32ul,
    "effect1" / EDTB1,
    "effect2" / EDTB1,
    "effect3" / EDTB1,
    "effect4" / EDTB1,
    "effect5" / EDTB1,
)

PPRM = Struct(
    Const(b"PPRM"),
    "length" / Int32ul,
    "pprm_dump" / Peek(HexDump(Bytes(this.length))),
    Padding(this.length),
)

ZPTC = Struct(
    "PTCF" / PTCF,
    "TXJ1" / TXJ1,
    "TXE1" / TXE1,
    "EDTB" / EDTB,
    "PPRM" / PPRM,
)


#--------------------------------------------------
import os
import sys
import mido
import binascii
from time import sleep

def printhex(direct, msg):
    print(direct)
    l = []
    numchar=0
    for n in msg:
        l.append(n)
        numchar=numchar+1
        if numchar % 8 == 0:
            print(" ".join( "{0:#0{1}x}".format(int( m ), 4) for m in l))
            l = []
    if l is not None:
        print(" ".join( "{0:#0{1}x}".format(int( m ), 4) for m in l))

def printExtrahex(direct, msg):
    print(direct + " 0xf0 ")
    printhex(direct, msg)
    print(direct + " 0xf7 ")

def sniffMidiOut(mtype, data, printme = False):
    if printme == True:
        print("sniffMidiOut")
        if mtype == "sysex":
            printExtrahex("===>    ", data)
        else:
            printhex("===>    ", data)
    return mido.Message(mtype, data = data)


def sniffMidiIn(self, printme = False):
    msg = self.inport.receive()
    if printme == True:
        print("sniffMidiIn")
        if msg.type == "sysex":
            printExtrahex("<====    ", msg.data)
        else:
            printhex("<====    ", msg.data)
    return msg


if sys.platform == 'win32':
    mido.set_backend('mido.backends.rtmidi_python')
    midiname = b"ZOOM G"
else:
    #midiname = "ZOOM GCE-3:ZOOM GCE-3 MIDI"
    midiname = "ZOOM G"

class zoomzt2(object):
    inport = None
    outport = None

    def is_connected(self):
        if self.inport == None or self.outport == None:
            return(False)
        else:
            return(True)

    def connect(self):
        for port in mido.get_input_names():
            print(port, midiname)
            if port[:len(midiname)]==midiname:
                self.inport = mido.open_input(port)
                #print("Using Input:", port)
                break
        for port in mido.get_output_names():
            print(port)
            if port[:len(midiname)]==midiname:
                self.outport = mido.open_output(port)
                #print("Using Output:", port)
                break

        if self.inport == None or self.outport == None:
            #print("Unable to find Pedal")
            return(False)

        # Enable PC Mode
        print("Enable PC Mode")
        data = [0x52, 0x00, 0x6e, 0x52]
        msg = sniffMidiOut("sysex", data)
        #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x52])
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)
        return(True)

    def disconnect(self):
        # Disable PC Mode
        print("Disable PC Mode")
        data = [0x52, 0x00, 0x6e, 0x53]
        msg = sniffMidiOut("sysex", data)
        #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x53])
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

        self.inport = None
        self.outport = None

    def pack(self, data):
        # Pack 8bit data into 7bit, MSB's in first byte followed
        # by 7 bytes (bits 6..0).
        packet = bytearray(b"")
        encode = bytearray(b"\x00")

        for byte in data:
            encode[0] = encode[0] + ((byte & 0x80) >> len(encode))
            encode.append(byte & 0x7f)

            if len(encode) > 7:
                packet = packet + encode
                encode = bytearray(b"\x00")

        # don't forget to add last few bytes
        if len(encode) > 1:
            packet = packet + encode

        return(packet)

    def unpack(self, packet):
        # Unpack data 7bit to 8bit, MSBs in first byte
        print("Packet length {}".format(len(packet)))
        data = bytearray(b"")
        loop = -1
        hibits = 0

        for byte in packet:
            if loop !=-1:
                if (hibits & (2**loop)):
                    data.append(128 + byte)
                else:
                    data.append(byte)
                loop = loop - 1
            else:
                hibits = byte
                # do we need to acount for short sets (at end of block block)?
                loop = 6

        return(data)

    def add_effect(self, data, name, version, id):
        print("add_effect")
        config = ZT2.parse(data)
        head, tail = os.path.split(name)
        
        group_new = (id & 0xFF000000) >> 24
        group_found = False

        for group in config[1]:
            if group['group'] == group_new:
                group_found = True
                effects = group['effects']
                slice = 0
                for effect in effects:
                    if effect['effect'] == tail:
                        del effects[slice]
                    slice = slice + 1

                new = dict(effect=tail, version=version, id=id)
                effects.append(new)

        if not group_found:
            effects = []
            new = dict(effect=tail, version=version, id=id, group=group_new)
            effects.append(new)
            new = dict(group=group_new, groupname=group_new, effects=effects, groupend=group_new)
            config[1].append(new)

        return ZT2.build(config)

    def add_effect_from_filename(self, data, name):
        binfile = open(name, "rb")
        if binfile:
            bindata = binfile.read()
            binfile.close()

            binconfig = ZD2.parse(bindata)
            head, tail = os.path.split(name)

            return self.add_effect(data, tail, binconfig['version'], binconfig['id'])
        return data


    def remove_effect(self, data, name):
        config = ZT2.parse(data)
        head, tail = os.path.split(name)
        
        for group in config[1]:
            effects = group['effects']
            slice = 0
            for effect in effects:
                if effect['effect'] == tail:
                    del effects[slice]
                slice = slice + 1

        return ZT2.build(config)

    def filename(self, packet, name):
        # send filename (with different packet headers)
        print(" send filename (with different packet headers")
        head, tail = os.path.split(name)
        for x in range(len(tail)):
            packet.append(ord(tail[x]))
        packet.append(0x00)

        msg = sniffMidiOut("sysex", data = packet)
        #msg = mido.Message("sysex", data = packet)
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)
        return(msg)

    def file_check(self, name):
        # check file is present on device
        print(" Checking file is present on device")
        packet = bytearray(b"\x52\x00\x6e\x60\x25\x00\x00")
        head, tail = os.path.split(name)
        self.filename(packet, tail)

        data = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00]
        msg = sniffMidiOut("sysex", data)
        #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00])
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)
        print(msg)
        if msg.data[6] == 127 and msg.data[7] == 127:
            return(False)
        print("We are checking the file HERE")
        data = [0x52, 0x00, 0x6e, 0x60, 0x27]
        msg = sniffMidiOut("sysex", data = data)
        #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x27])
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)
        print(msg)
        return(True)
    
    def file_wild(self, first):
        if first:
            packet = bytearray(b"\x52\x00\x6e\x60\x25\x00\x00")
        else:
            packet = bytearray(b"\x52\x00\x6e\x60\x26\x00\x00")
        msg = self.filename(packet, "*")

        if msg.data[4] == 4:
            for x in range(14,27):
                if msg.data[x] == 0:
                    return bytes(msg.data[14:x]).decode("utf-8")
        else:
            return ""

    def file_download(self, name):
        # download file from pedal to PC
        print("In file_download {}".format(name))
        packet = bytearray(b"\x52\x00\x6e\x60\x20\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00")
        print("packet")
        head, tail = os.path.split(name)
        self.filename(packet, tail)

        msg = sniffMidiOut("sysex", data = packet)
        # msg = mido.Message("sysex", data = packet)
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)
        
        # Read parts 1 through 17 - refers to FLST_SEQ, possibly larger
        data = bytearray(b"")
        while True:
            sData = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00]
            msg = sniffMidiOut("sysex", data=sData)
            #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00])
            self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

            #sData = [0x52, 0x00, 0x6e, 0x60, 0x22, 0x14, 0x2f, 0x60, 0x00, 0x0c, 0x00, 0x04, 0x00, 0x00, 0x00]
            sData = [0x52, 0x00, 0x6e, 0x60, 0x22, 0x14, 0x2f, 0x60, 0x00, 0x0c, 0x00, 0x02, 0x00, 0x00, 0x00]
            msg = sniffMidiOut("sysex", data=sData)
            #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x22, 0x14, 0x2f, 0x60, 0x00, 0x0c, 0x00, 0x04, 0x00, 0x00, 0x00])
            self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

            sData = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00]
            msg = sniffMidiOut("sysex", data=sData)
            #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00])
            self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

            #decode received data
            packet = msg.data
            length = int(packet[9]) * 128 + int(packet[8])
            # 2047 is a "I dont exist"
            if length == 0 or length == 2047:
                print("WE GOT ZERO LEN BACK")
                break
            print("WE GOT {} LEN BACK".format(length))
            block = self.unpack(packet[10:10 + length + int(length/7) + 1])

            print("HERE IS THE BLOCK!! {} from {}".format(len(block), len(packet)+2))
            #printhex("BLOCK ", block, False)
            # confirm checksum (last 5 bytes of packet)
            # note: mido packet does not have SysEx prefix/postfix
            checksum = packet[-5] + (packet[-4] << 7) + (packet[-3] << 14) \
                    + (packet[-2] << 21) + ((packet[-1] & 0x0F) << 28) 
            if (checksum ^ 0xFFFFFFFF) == binascii.crc32(block):
                data = data + block
            else:
                print("Checksum error", hex(checksum))
                break
        return(data)

    def file_upload(self, name, data):
        packet = bytearray(b"\x52\x00\x6e\x60\x24")
        head, tail = os.path.split(name)
        self.filename(packet, tail)

        packet = bytearray(b"\x52\x00\x6e\x60\x20\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00")
        head, tail = os.path.split(name)
        self.filename(packet, tail)

        d1 = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00]
        msg = sniffMidiOut("sysex", d1 )
        # msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00])
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

        while len(data):
            packet = bytearray(b"\x52\x00\x6e\x60\x23\x40\x00\x00\x00\x00")
            if len(data) > 512:
                length = 512
            else:
                length = len(data)
            packet.append(length & 0x7f)
            packet.append((length >> 7) & 0x7f)
            packet = packet + bytearray(b"\x00\x00\x00")

            packet = packet + self.pack(data[:length])

            # Compute CRC32
            crc = binascii.crc32(data[:length]) ^ 0xFFFFFFFF
            packet.append(crc & 0x7f)
            packet.append((crc >> 7) & 0x7f)
            packet.append((crc >> 14) & 0x7f)
            packet.append((crc >> 21) & 0x7f)
            packet.append((crc >> 28) & 0x0f)

            data = data[length:]
            #print(hex(len(packet)), binascii.hexlify(packet))

            msg = sniffMidiOut("sysex", data = packet)
            # msg = mido.Message("sysex", data = packet)
            self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

            sData = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00]
            msg = sniffMidiOut("sysex", data = sData)
            # msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x05, 0x00])
            self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

    def file_delete(self, name):
        packet = bytearray(b"\x52\x00\x6e\x60\x24")
        head, tail = os.path.split(name)
        self.filename(packet, tail)

    def file_close(self):
        data = [0x52, 0x00, 0x6e, 0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00]
        msg = sniffMidiOut("sysex", data)
        #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00])
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)
        
        data = [0x52, 0x00, 0x6e, 0x60, 0x09]
        msg = sniffMidiOut("sysex", data)
        #msg = mido.Message("sysex", data = [0x52, 0x00, 0x6e, 0x60, 0x09])
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)
 
 
    def patch_download(self, location):
        print("patch_download")
        packet = bytearray(b"\x52\x00\x6e\x09\x00")
        packet.append(int(location/10)-1)
        packet.append(location % 10)

        msg = sniffMidiOut("sysex", data = packet)
        #msg = mido.Message("sysex", data = packet)
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

        # decode received data
        packet = msg.data
        length = int(packet[8]) * 128 + int(packet[7])
        if length == 0:
            return()
        data = self.unpack(packet[9:9 + length + int(length/7) + 1])

        # confirm checksum (last 5 bytes of packet)
        checksum = packet[-5] + (packet[-4] << 7) + (packet[-3] << 14) \
                + (packet[-2] << 21) + ((packet[-1] & 0x0F) << 28) 

        if (checksum ^ 0xFFFFFFFF) != binascii.crc32(data):
            print("Checksum error", hex(checksum))

        return(data)


    def patch_upload(self, location, data):
        packet = bytearray(b"\x52\x00\x6e\x08\x00")
        packet.append(int(location/10)-1)
        packet.append(location % 10)

        length = len(data)
        packet.append(length & 0x7f)
        packet.append((length >> 7) & 0x7f)

        packet = packet + self.pack(data[:length])

        # Compute CRC32
        crc = binascii.crc32(data[:length]) ^ 0xFFFFFFFF
        packet.append(crc & 0x7f)
        packet.append((crc >> 7) & 0x7f)
        packet.append((crc >> 14) & 0x7f)
        packet.append((crc >> 21) & 0x7f)
        packet.append((crc >> 28) & 0x0f)

        #print(hex(len(packet)), binascii.hexlify(packet))

        msg = sniffMidiOut("sysex", data = packet)
        #msg = mido.Message("sysex", data = packet)
        self.outport.send(msg); sleep(0); msg = sniffMidiIn(self)

    '''
    def patch_download_current(self):
        packet = bytearray(b"\x52\x00\x6e\x29")

    def patch_upload_current(self, data):
        packet = bytearray(b"\x52\x00\x6e\x28")
    '''
    def getfile(self, name):
        print("options.receive - getting ", name)
        state = self.file_check(name)
        if (state == False):
            self.disconnect()
            sys.exit("Filename doesnt exist")
        data = self.file_download(name)        
        self.file_close()
        binconfig = ZD2.parse(data)
        # print(binconfig)

        if len(data) > 0x88:
            fileSize=((((data[0x88+2+ 3] * 256) + data[0x88+2 + 2] * 256) + data[0x88 + 2 + 1] * 256) + data[0x88+2 + 0])
            outBMfile = open(name + ".BMP", "wb")
            if not outBMfile:
                sys.exit("Unable to open FILE for writing")
            outBMfile.write(data[0x88:0x88+fileSize])
            outBMfile.close()
            # print("Writing to")
            outfile = open(name, "wb")
            if not outfile:
                sys.exit("Unable to open FILE for writing")
            # print("data is ", len(data))
            outfile.write(data)
            outfile.close()
            # lets find the OnOff
            OnOffstart = data.find("OnOff".encode())
            mmax = []
            mdefault = []
            if OnOffstart != 0:
                print("In OnOffstart")
                for j in range(0, 10):
                    mmax.append(data[OnOffstart + j * 0x38 + 12] + 
                        data[OnOffstart + j * 0x38 + 13] * 256)
                    mdefault.append(data[OnOffstart + j * 0x38 + 16] + 
                    data[OnOffstart + j * 0x38 + 17] * 256);
                print(mmax[j])
                print(mdefault[j])

            # lets find the TXE1
            TXE1start = data.find("TXE1".encode())
            TXdescription = ""
            if TXE1start != 0:
                # ts is beginning of TXE1, 4 chars.
                ts = TXE1start + 4
                fileSize=((((data[ts + 3] * 256) + data[ts + 2] * 256) + data[ts+ 1] * 256) + data[ts + 0])

                # but now we need to offset the 4 chars for len
                for j in range(4, fileSize + 4):
                    if data[j + ts] != 0x0a and data[j + ts] != 0x0d:
                        TXdescription = TXdescription + chr(data[j + ts])
            print("Desc " + TXdescription)
            # so now we try to find the English params?
            PRMEstart = data.find("PRME".encode())
            if PRMEstart != 0:
                j = 0
                y = data[PRMEstart:-1]
                # start of the Parameters inside English
                Paramstart = y.find("Parameters".encode())
                # now cut from start of Parameters, we want
                # to start at the []
                newy = y[Paramstart:-1]
                bracketstart = newy.find("[".encode())
                myParams=""
                myOffset=bracketstart
                while chr(newy[myOffset + j]) != ']':
                    if newy[myOffset + j] != 0x0a and newy[myOffset + j] != 0x0d:
                        myParams = myParams + chr(newy[myOffset + j])
                    else:
                        myParams = myParams + " "
                    j=j+1
                myParams=myParams + ']'
                x = json5.loads(myParams)
                for j in range(0, len(x)):
                    x[j]['mmax'] = mmax[j+2]
                    x[j]['mdefault'] = mdefault[j+2]
                print(x)
                # get description the hard way.
                xAdd = {
                    "FX" : 
                    { 
                        "name": binconfig['name'],
                        "description": TXdescription,
                        "version": binconfig['version'],
                        "fxid": (binconfig['id'] & 0xFFFF),
                        "gid": ((binconfig['id'] & 0xFFFF0000) >> 16) >> 5,
                        "group": binconfig['group'], 
                        "numParams": len(x),
                        "numSlots": math.ceil(len(x) / 4),
                        "filename": name + '.BMP'
                    }
                }
                out_file = open(name + ".json", "w")
                xAdd['Parameters'] = x
                json5.dump(xAdd, out_file, indent = 6)
                out_file.close()
            return xAdd 

    def allpatches(self, total_pedal = None, fxLookup = None):
        thesePatches = []
        for i in range(10, 60):
            data = self.patch_download(i)
            outfile = open("patch_{}".format(i), "wb")
            if not outfile:
                sys.exit("Unable to open FILE for writing")
            outfile.write(data)
            outfile.close()
            thisPatch = {}
            if data:
                config = ZPTC.parse(data)
                #print(config)
                print("PatchNumber: {}".format(i))
                numFX = (config['PTCF']['effects'])
                thisPatch['numFX'] = numFX
                patchName = (config['PTCF']['name'])
                thisPatch['patchname'] = patchName
                patchDescription = (config['TXE1']['name'])
                thisPatch['description'] = patchDescription
                print ("Patch: {}".format(patchName))
                print ("Desc: {}".format(patchDescription))
                theseFX = []
                for fx in range(1, numFX + 1):
                    thisFX={}
                    idN = "id{}".format(fx)
                    effectN = "effect{}".format(fx)
                    print("  enabled: ",config['EDTB'][effectN]['reversed']['control']['enabled'])
                    currID = config['EDTB'][effectN]['reversed']['control']['id']
                    print("  FXID={}, GID={}".format(str(currID & 0xFFFF), str( ( (currID&0xFFFF0000)>>16)>>5) ) )
                    thisFX['fxid'] = (currID & 0xFFFF)
                    thisFX['gid'] = (currID & 0xFFFF0000)>>21
                    thisFX['enabled'] = config['EDTB'][effectN]['reversed']['control']['enabled']
                    # assume numParameters is 8, unless we already looked up FX and have a hit.
                    np = 8
                    npi = -1
                    fxName=""
                    fxDescription=""
                    fxVersion=""
                    fxFilename=""
                    fxnumSlots=1
                    if fxLookup is not None and total_pedal is not None:
                        try:
                            npi = fxLookup[thisFX['fxid'], thisFX['gid']]
                            baseFX = total_pedal[npi]['FX']
                            np = baseFX['numParams']
                            fxName = baseFX['name']
                            fxVersion = baseFX['version']
                            fxDescription = baseFX['description']
                            fxFilename = baseFX['filename']
                            fxnumSlots = baseFX['numSlots']
                        except:
                            np = 8
                    thisFX['name'] = fxName
                    thisFX['description'] = fxDescription
                    thisFX['version'] = fxVersion
                    thisFX['numSlots'] = fxnumSlots
                    thisFX['filename'] = fxFilename
                    thisFX['Parameters'] = []
                    for j in range(1,np+1):
                        pj = "param{}".format(j)
                        thisParam = {}
                        if npi != -1:
                            baseP = total_pedal[npi]['Parameters'][j - 1]
                            thisParam = {
                                    pj: config['EDTB'][effectN]['reversed']['control'][pj],
                                    "name" : baseP['name'],
                                    "explanation": baseP['explanation'],
                                    "blackback": baseP['blackback'],
                                    "pedal": baseP['pedal'],
                                    "mmax": baseP['mmax'],
                                    "mdefault": baseP['mdefault']
                                    }
                        else:
                            print("   {} = {}".format(pj, config['EDTB'][effectN]['reversed']['control'][pj]))
                            thisParam = {pj: config['EDTB'][effectN]['reversed']['control'][pj]}
                        thisFX['Parameters'].append(thisParam)
 
                    theseFX.append(thisFX)
                thisPatch['FX'] = theseFX        
                print(thisPatch)
                thesePatches.append(thisPatch)
        print("PRINTING THESE PATCHES")
        print(thesePatches)
        out_file = open("allpatches.json", "w")
        json5.dump(thesePatches, out_file, indent = 4)
        out_file.close()
        
#--------------------------------------------------
def main():
    from optparse import OptionParser

    data = bytearray(b"")
    print("in main .. data is ...")
    pedal = zoomzt2()

    usage = "usage: %prog [options] FILENAME"
    parser = OptionParser(usage)
    parser.add_option("-d", "--dump",
        help="dump configuration to text",
        action="store_true", dest="dump")
    parser.add_option("-s", "--summary",
        help="summarized configuration in human readable form",
    action="store_true", dest="summary")
    parser.add_option("-b", "--build",
        help="output commands required to build this FLTS_SEQ",
        dest="build")
    
    parser.add_option("-A", "--add",
        help="add effect to FLST_SEQ", dest="add")
    parser.add_option("-v", "--ver",
        help="effect version (use with --add)", dest="ver")
    parser.add_option("-i", "--id",
        help="effect id (use with --add)", dest="id")
    parser.add_option("-D", "--delete",
    help="delete effect from FLST_SEQ", dest="delete")
    
    parser.add_option("-t", "--toggle",
        help="toggle install/uninstall state of effect NAME in FLST_SEQ", dest="toggle")

    parser.add_option("-w", "--write", dest="write",
        help="write config back to same file", action="store_true")
    parser.add_option("-g", "--getfile",
        help="getfile from Zoom", dest="getfile")


    # interaction with attached device
    parser.add_option("-R", "--receive",
        help="Receive FLST_SEQ from attached device",
        action="store_true", dest="receive")
    parser.add_option("-S", "--send",
        help="Send FLST_SEQ to attached device",
        action="store_true", dest="send")
    parser.add_option("-I", "--install",
        help="Install effect binary to attached device", dest="install")
    parser.add_option("-U", "--uninstall",
        help="Remove effect binary from attached device", dest="uninstall")

    # attached device's effect patches
    parser.add_option("-p", "--patch",
        help="download specific patch (10..59)", dest="patch")
    # all attached device patches
    parser.add_option("-a", "--allpatches",
        help="download all patches (10..59)")
    parser.add_option("-P", "--upload",
        help="upload specific patch (10..59)", dest="upload")

    (options, args) = parser.parse_args()
    print(options)
    print(args)
    if len(args) != 1:
        parser.error("FILE not specified")

    if options.getfile:
        print("options: ", options.getfile)
        print("args[0] = ", args[0])

    if options.install and options.uninstall:
        sys.exit("Cannot use 'install' and 'uninstall' at same time")

    if options.patch:
        if int(options.patch) < 10 or int(options.patch) > 59:
            sys.exit("Patch number should be between 10 and 59")

    if options.upload:
        if int(options.upload) < 10 or int(options.upload) > 59:
            sys.exit("Patch number should be between 10 and 59")

    if options.receive or options.send or options.install or options.patch or options.upload or options.getfile:
        if not pedal.connect():
            sys.exit("Unable to find Pedal")

    if options.patch:
        print("options.patch")
        data = pedal.patch_download(int(options.patch))
        pedal.disconnect()

        outfile = open(args[0], "wb")
        if not outfile:
            sys.exit("Unable to open FILE for writing")

        outfile.write(data)
        outfile.close()
        exit(0)

    if options.allpatches:
        print("options.allpatches")

        pedal.allpatches()

        pedal.disconnect()

        exit(0)


    if options.upload:
        infile = open(args[0], "rb")
        if not infile:
            sys.exit("Unable to open FILE for reading")
        else:
            data = infile.read()
        infile.close()

        if len(data):
            data = pedal.patch_upload(int(options.upload), data)
        pedal.disconnect()

        exit(0)

    if options.getfile:
        pedal.getfile(options.getfile)

    if options.receive:
        pedal.file_check("FLST_SEQ.ZT2")
        data = pedal.file_download("FLST_SEQ.ZT2")
        print("options.receive - getting FLST_SEQ.ZT2")
        pedal.file_close()

        # so now interpret the data to get the ZD2's.
        # and for each call getfile(name)
        # we also create a total pedal JSON
        total_pedal = [{
            "FX": {
                "name": "Bypass",
                "description": "No effect.",
                "version": "1.00",
                "fxid": 0,
                "gid": 0,
                "group": 0,
                "numParams": 0,
                "numSlots": 1,
                "filename": ""
            },
            "Parameters": []
            }
        ]

        fxLookup = {}
        fxLookup[0, 0] = 0
        j = 1
        # we need to create a "blank" entry for BYPASS
        config = ZT2.parse(data)
        for group in config[1]:
            print("Group", dict(group)["group"], ":", dict(group)["groupname"])
    
            for effect in dict(group)["effects"]:
                myG = dict(effect)["id"]
                myGID = ((myG & 0xFFFF0000) >> 16) >> 5
                myID = (myG & 0xFFFF)
                print("myID is ", myID, " ", hex(myID))
                print("myGID is ", int(myGID), " ", hex(int(myGID)))
                print("   ", dict(effect)["effect"], "(ver=", dict(effect)["version"], \
                    "), group=", dict(effect)["group"], ", id=", hex(dict(effect)["id"]), \
                    ", installed=", dict(effect)["installed"])
                print("Getting {}".format(dict(effect)["effect"]))
                currFX = pedal.getfile(dict(effect)["effect"])
                total_pedal.append(currFX)
                fxLookup[myID, myGID] = j 
                j = j + 1
        out_file = open("allfx.json", "w")
        json5.dump(total_pedal, out_file, indent = 6)
        out_file.close()

        # now find list of Patches, pass in the fxLookup and total_pedal
        pedal.allpatches(total_pedal = total_pedal, fxLookup = fxLookup)
    else:
        # Read data from file
        infile = open(args[0], "rb")
        if not infile:
            sys.exit("Unable to open config FILE for reading")
        else:
            data = infile.read()
        infile.close()

    if options.add and options.ver and options.id:
        if options.id[:2] == "0x":
            data = pedal.add_effect(data, options.add, options.ver, int(options.id, 16))
        else:
            data = pedal.add_effect(data, options.add, options.ver, int(options.id))

    if options.delete:
        data = pedal.remove_effect(data, options.delete)
    
    if options.dump and data:
        print("dump")
        config = ZT2.parse(data)
        print(config)
    
    if options.toggle and data:
        print("toggle")
        config = ZT2.parse(data)
        groupnum=0
    
        for group in config[1]:
            for effect in dict(group)["effects"]:
                if dict(effect)["effect"] == options.toggle:
                    if dict(effect)["installed"] == 1:
                        config[1][groupnum]["effects"][0]["installed"] = 0
                    else:
                        config[1][groupnum]["effects"][0]["installed"] = 1

            groupnum = groupnum + 1
        data = ZT2.build(config)
    
    if options.summary and data:
        print("summary")
        config = ZT2.parse(data)
        for group in config[1]:
            print("Group", dict(group)["group"], ":", dict(group)["groupname"])
    
            for effect in dict(group)["effects"]:
                myG = dict(effect)["id"]
                myGID = ((myG & 0xFFFF0000) >> 16) >> 5
                myID = (myG & 0xFFFF)
                print("myID is ", myID, " ", hex(myID))
                print("myGID is ", int(myGID), " ", hex(int(myGID)))
                print("   ", dict(effect)["effect"], "(ver=", dict(effect)["version"], \
                    "), group=", dict(effect)["group"], ", id=", hex(dict(effect)["id"]), \
                    ", installed=", dict(effect)["installed"])

    if options.build and data:
        print("options.build")
        config = ZT2.parse(data)
        for group in config[1]:
            for effect in dict(group)["effects"]:
                print("python3 zoomzt2_shooking.py -i ", hex(dict(effect)["id"]), \
                    "-A", dict(effect)["effect"], "-v", dict(effect)["version"], \
                    "-w", options.build)

    if options.write and data:
       print("options.write")
       outfile = open(args[0], "wb")
       if not outfile:
           sys.exit("Unable to open FILE for writing")
    
       outfile.write(data)
       outfile.close()

    binfile = None
    if options.install:
        # Read data from file
        binfile = open(options.install, "rb")
        if infile:
            bindata = binfile.read()
            binfile.close()

            pedal.file_check(options.install)
            pedal.file_upload(options.install)

    if options.uninstall:
        pedal.file_check(options.uninstall)
        pedal.file_delete(options.uninstall)

    if options.send:
        pedal.file_check("FLST_SEQ.ZT2")
        pedal.file_upload("FLST_SEQ.ZT2", data)
    
    if options.send or options.install or options.uninstall:
        pedal.file_close()
    
    if pedal.is_connected():
        pedal.disconnect()
    
if __name__ == "__main__":
    main()
