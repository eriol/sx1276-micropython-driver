# Copyright (C) 2023 Salvatore Sanfilippo <antirez@gmail.com>
# All Rights Reserved
#
# This code is released under the BSD 2 clause license.
# See the LICENSE file for more information

import cryptolib, hashlib, os

# This class implements the packets encryption keychain. It loads and
# saves keys from/to disk, and implements encryption and decryption.
class Keychain:
    def __init__(self,keychain_dir="keys"):
        try: os.mkdir(keychain_dir)
        except: pass
        self.keychain_dir = keychain_dir
        self.load_keys()

    # Load keys in memory.
    def load_keys(self):
        self.keys = {}  # Map "key name" -> SHA256(key)
        for key_name in os.listdir(self.keychain_dir):
            try:
                f = open(self.keychain_dir+"/"+key_name,'rb')
                key = f.read()
                f.close()
                self.keys[key_name] = self.sha16(key)
            except: pass

    # Return all the available key names
    def list_keys(self):
        return os.listdir(self.keychain_dir)

    # Delete the specified key
    def del_key(self,key_name):
        try: os.unlink(self.keychain_dir+"/"+key_name)
        except: pass
        del self.keys[key_name]

    # Add a new key into the keychain, overwriting an old one
    # with the same name if any.
    def add_key(self,key_name,key):
        f = open(self.keychain_dir+"/"+key_name,'wb')
        f.write(key)
        f.close()
        self.load_keys()

    # Return the SHA256 digest truncated to 16 bytes
    def sha16(self,data):
        return hashlib.sha256(data).digest()[:16]

    # This function expects an already encoded data packet, and
    # return its encrypted version.
    def encrypt(self,packet,key_name):
        key = self.keys.get(key_name)
        if key == None:
            raise Exception("No key with the specified name")
        # Compute the IV and digest with TTL set to 0, as it could
        # change as the packet gets relayed by the network.
        copy = packet[:3] + b'\x00' + packet[4:]
        iv = self.sha16(copy[:11])
        checksum = self.sha16(copy)[:9]
        # Set the last byte of the checksum to 1, so that the padding
        # will be always recognizable as the sequence of trailing zeros.
        checksum = checksum[:8] + bytes([checksum[8]|1]) + checksum[9:]
        payload = copy[11:] + checksum
        if (len(payload) % 16): payload += b'\x00' * (16-(len(payload) % 16))
        encr = cryptolib.aes(key,2,iv).encrypt(payload)
        # The final encrypted packet is the original header
        # plus the encrypted part, from the sender ID to the final checksum.
        return packet[:11] + encr

    # Try every possible key, trying to decrypt the packet. Is
    # no match is found, None is returned, otherwise the method returns
    # a two items array: [key_name, decripted_packet].
    def decrypt(self,encr):
        for key_name in self.keys:
            key = self.keys[key_name]
            header = encr[:11]
            payload = encr[11:]

            # Set TTL to zero for the IV
            copy = header[:3] + b'\x00' + header[4:]
            iv = self.sha16(copy)

            # Decrypt and see if checksum matches
            plain = cryptolib.aes(key,2,iv).decrypt(payload)
            idx = len(plain)-1
            # Seek first non-zero byte, to discard the padding
            while idx > 11 and plain[idx] == 0: idx -= 1
            claimed_checksum = plain[idx+1-9:idx+1] # Last 9 bytes but padding
            plain = plain[:idx+1-9] # Remove final 9 bytes of checksum
            # Now recompute the checksum, and see if it's the same.
            checksum = self.sha16(copy+plain)[:9]
            checksum = checksum[:8] + bytes([checksum[8]|1]) + checksum[9:]
            if checksum == claimed_checksum:
                return [key_name,header+plain]
        return None

if __name__ == "__main__":
    kc = Keychain()
    kc.add_key("freaknet","morte")
    test_packet = b"TF" + "IDID" + "T" + "IVIV" + "SENDER" + "foo: bar"
    #print(test_packet)
    encr = kc.encrypt(test_packet,"freaknet")
    #print(encr)
    decr = kc.decrypt(encr)
    #print(decr)
    if test_packet == decr[1]:
        print("Packet encrypted and decrypred with success: got same bytes")
    # Flipping a bit somewhere should no longer result in a valid packet
    corrupted = encr[:18] + bytes([encr[18]^1]) + encr[19:]
    decr = kc.decrypt(corrupted)
    if decr == None:
        print("Corrupted packet correctly refused")