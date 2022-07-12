import crcmod

crcfunc = crcmod.mkCrcFun(0x107, rev=False, initCrc=0x00, xorOut=0x00)

bytes_to_send = "Ahoj, moja toto"
print(f"bytes_to_send.encode(): {bytes_to_send}")

crc = crcfunc(bytes_to_send.encode())
print(f"crc: {crc}")
