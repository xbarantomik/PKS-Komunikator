import socket
import struct
import crcmod
import os
import threading
import time
import math
import random
import string


#....flags........................................................................................
SFH_MSG = 51        #0x33       Special First Header for Message
SFH_FIL = 52        #0x34       Special First Header for File
SFH_ACK = 53        #0x35

DATA = 11           #0x0b
ACK = 12            #0x0c
REP = 83            #0x53       Repeat after CRC-fail
FIN = 99            #0x63
UPD = 29            #0x1d       Update for Keep Alive
UPD_END_CON = 25    #0x19       Update End, next acion Continue
UPD_END_QUT = 26    #0x1a       Update End, next action Quit


recv_ack_nack = 0
recv_ack_nack_file_name = 0


#....globalne prememne.............................................................................
# interval
keep_alive_interval = 10

# input oboch stran
fragment_size = 0
server_ip_port = (0, 0)

#keep alive boolean
keep_alive_status = [False, 0]  #[1] bude flag o ackii klienta (UPD_END_CON / UPD_END_QUT)


#....vytvorenie socketu a funkcia na CRC...........................................................
crcfunc = crcmod.mkCrcFun(0x107, initCrc=0x00, xorOut=0x00)
client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


#....poslielanie keep alive packetov...............................................................
def keeping_alive(alive_time):
    while 1:
        if keep_alive_status[0]:
            head = struct.pack('!h', UPD)
            client_sock.sendto(head, server_ip_port)
            time.sleep(alive_time / 3)
            print(f"Keeping alive the connection ({alive_time}s)")
            for i in range(2):
                if not keep_alive_status[0]:
                    if keep_alive_status[1] == UPD_END_CON:
                        head = struct.pack('!h', UPD_END_CON)
                        client_sock.sendto(head, server_ip_port)
                    else:
                        head = struct.pack('!h', UPD_END_QUT)
                        client_sock.sendto(head, server_ip_port)
                    keep_alive_status[1] = 0
                    return
                time.sleep(alive_time / 3)
        else:
            if keep_alive_status[1] == UPD_END_CON:
                head = struct.pack('!h', UPD_END_CON)
                client_sock.sendto(head, server_ip_port)
            else:
                head = struct.pack('!h', UPD_END_QUT)
                client_sock.sendto(head, server_ip_port)
            keep_alive_status[1] = 0
            return


#....vytvorenie threadu na keep alive..............................................................
def start_thread(alive_time):
    thread = threading.Thread(target=keeping_alive, args=(alive_time,))
    thread.daemon = True
    thread.start()
    return thread


#....input IP a Port...............................................................................
def get_ip_port():
    global server_ip_port
    # ip = input("\nInput server IP address: ")
    ip = "127.0.0.1"
    print(f"\nInput server IP address: ... {ip}")
    while 1:
        try:
            port = int(input("Input server Port      : "))
        except ValueError:
            print("It has to be a whole number")
        else:
            break

    # port = 25000
    # print(f"Input server Port:       ... {port}")

    # nadviazanie komunikacie
    server_ip_port = (ip, port)
    client_sock.sendto(str.encode(''), server_ip_port)
    print("\n--------Connection was established--------\n")


#....poskodenie dat na odoslanie...................................................................
def crc_fail(num, bytes_to_send):
    # prvy byte sa v datach sa zmeni
    origi_byte = bytes_to_send[0]
    rand_char = random.choice(string.printable)
    while origi_byte == rand_char:
        rand_char = random.choice(string.digits)

    if num == 1:
        return rand_char
    elif num == 2:
        return rand_char, 1


#....posielanie spravy.............................................................................
def send_message(fragments_to_send, message):
    global recv_ack_nack
    random_index = random.randint(1, fragments_to_send)
    count = 0
    index = 1

    print(f"\nRandom double CRC Fail - Fragment number {random_index}\n")

    while 1:

        bytes_to_send = message[:fragment_size]
        message = message[fragment_size:]

        crc = crcfunc(bytes_to_send.encode())
        head = struct.pack('!hii', DATA, crc, index)

        # pri random_index sa posle poskodeny fragment
        if random_index == index:
            new_first_byte = crc_fail(1, bytes_to_send)
            damaged_bytes_to_send = new_first_byte + bytes_to_send[1:]
            fin_bytes = head + damaged_bytes_to_send.encode()
        else:
            fin_bytes = head + bytes_to_send.encode()
        client_sock.sendto(fin_bytes, server_ip_port)

        reply = client_sock.recvfrom(fragment_size)
        m = struct.unpack_from('!h', reply[0])
        # ak server prijal chybne crc
        if m[0] == REP:
            while 1:
                crc_rep = crcfunc(bytes_to_send.encode())
                head = struct.pack('!hii', DATA, crc_rep, index)
                # pri prvom opakovani sa poslu poskodene data este raz
                if count == 0:
                    new_first_byte, count = crc_fail(2, bytes_to_send)
                    damaged_bytes_to_send = new_first_byte + bytes_to_send[1:]
                    fin_bytes = head + damaged_bytes_to_send.encode()
                else:
                    fin_bytes = head + bytes_to_send.encode()
                client_sock.sendto(fin_bytes, server_ip_port)

                reply_again = client_sock.recvfrom(fragment_size)
                r = struct.unpack_from('!h', reply_again[0])
                # print("rep " + str(index))
                if r[0] == ACK:
                    # print("repACK " + str(index))
                    recv_ack_nack += 1
                    index += 1
                    break
                recv_ack_nack += 1
        elif m[0] == ACK:
            # print("ACK " + str(index))
            recv_ack_nack += 1
            index += 1
            pass
        else:
            print("nieco ine nez ACK a REP prislo")

        # kontrola ci sa poslali uz vsetky fragmenty
        if index == fragments_to_send + 1:
            recv_ack_nack += 1
            print(f"Number of all ACK and NACK: {recv_ack_nack}")
            break


#....posielanie ostatnych special first header-ov pre subor, data su nazov suboru..................
def send_sfh(file_name):

    frags = math.ceil(len(file_name) / fragment_size)

    for index in range(frags):
        bytes_to_send = file_name[:fragment_size]
        file_name = file_name[fragment_size:]
        crc = crcfunc(bytes_to_send.encode())

        head = struct.pack('!hii', SFH_FIL, frags, crc)
        fin_bytes = head + bytes_to_send.encode()
        client_sock.sendto(fin_bytes, server_ip_port)

        reply = client_sock.recvfrom(fragment_size)
        f = struct.unpack_from('!h', reply[0])
        # ak server prijal chybne crc
        if f[0] == REP:
            while 1:
                crc_rep = crcfunc(bytes_to_send.encode())
                head = struct.pack('!hii', SFH_FIL, 0, crc_rep)
                fin_bytes = head + bytes_to_send.encode()
                client_sock.sendto(fin_bytes, server_ip_port)

                reply_again = client_sock.recvfrom(fragment_size)
                r = struct.unpack_from('!h', reply_again[0])
                if r[0] == SFH_ACK:
                    break
        elif f[0] == SFH_ACK:
            pass
        else:
            print("nieco ine nez ACK a REP prislo")


#....posielanie suboru.............................................................................
def send_file(file, fragments_to_send):
    global recv_ack_nack
    random_index = random.randint(1, fragments_to_send)
    count = 0
    index = 1

    print(f"\nRandom double CRC Fail - Fragment number {random_index}\n")

    while 1:
        bytes_to_send = file[:fragment_size]
        file = file[fragment_size:]
        crc = crcfunc(bytes_to_send)
        # prvy packet s datami bude mat namiesto indexu pocet fragmentov
        if index == 1:
            head = struct.pack('!hii', DATA, crc, fragments_to_send)
        else:
            head = struct.pack('!hii', DATA, crc, index)

        # pri random_index sa posle poskodeny fragment
        if random_index == index:
            new_first_byte = crc_fail(1, bytes_to_send)
            damaged_bytes_to_send = new_first_byte + bytes_to_send.decode('ISO-8859-1')[1:]
            damaged_bytes_to_send = damaged_bytes_to_send.encode('ISO-8859-1')
            fin_bytes = head + damaged_bytes_to_send
        else:
            fin_bytes = head + bytes_to_send

        client_sock.sendto(fin_bytes, server_ip_port)

        reply = client_sock.recvfrom(fragment_size)
        m = struct.unpack_from('!h', reply[0])
        # ak server prijal chybne crc
        if m[0] == REP:
            while 1:
                crc_rep = crcfunc(bytes_to_send)
                head = struct.pack('!hii', DATA, crc_rep, index)
                # pri prvom opakovani sa poslu poskodene data este raz
                if count == 0:
                    new_first_byte, count = crc_fail(2, bytes_to_send)
                    damaged_bytes_to_send = new_first_byte + bytes_to_send.decode('ISO-8859-1')[1:]
                    damaged_bytes_to_send = damaged_bytes_to_send.encode('ISO-8859-1')
                    fin_bytes = head + damaged_bytes_to_send
                else:
                    fin_bytes = head + bytes_to_send
                client_sock.sendto(fin_bytes, server_ip_port)

                reply_again = client_sock.recvfrom(fragment_size)
                r = struct.unpack_from('!h', reply_again[0])
                if r[0] == ACK:
                    recv_ack_nack += 1
                    index += 1
                    break
                recv_ack_nack += 1
        elif m[0] == ACK:
            recv_ack_nack += 1
            index += 1
            pass
        else:
            print("nieco ine nez ACK a REP prislo")

        # kontrola ci sa poslali uz vsetky fragmenty
        if index == fragments_to_send + 1:
            recv_ack_nack += 1
            print(f"Number of all ACK and NACK: {recv_ack_nack}")
            break


def run_client():
    global fragment_size

    #....nastavenie MTU............................................................................
    while 1:
        try:
            fragment_size = int(input("Input fragment size: "))
            # fragment_size = 3
            # print(f"Input fragment size:  ...{fragment_size}")
            while (fragment_size <= 0) or (fragment_size > 1462):
                if fragment_size <= 0:
                    fragment_size = int(input("Has to be greater than 0: "))
                else:
                    fragment_size = int(input("Has to be equal or less than 1462: "))
        except ValueError:
            print("It has to be a whole number")
        else:
            break

    client_sock.sendto((str(fragment_size)).encode(), server_ip_port)

    #....vyber subor, sprava alebo sa quit.....................................................
    print("\n--------Choose--------\nf - to send a FILE\nm - to send a MESSAGE\nq - to exit the program")
    choice = input().lower()
    while not (choice == 'f' or choice == 'm' or choice == 'q'):
        choice = input("Try again!\nf - to send a FILE\nm - to send a MESSAGE\nq - to quit\n").lower()

    #....podla vyberu pokracuje dalej..............................................................
    #....ak q tak program vypne....................................................................
    if choice == 'q':
        fin_head = struct.pack('!hii', FIN, 0, 0)
        client_sock.sendto(fin_head, server_ip_port)
        client_sock.close()
        print("\n-----------------------------End of the program---------------------------------")
        quit()
    else:
        if choice == 'm':
            msg = input("\n--------Sending a MESSAGE--------\nEnter your message:\n")
            num_of_frag = math.ceil(len(msg) / fragment_size)
            print(f"\nNumber of fragments: {num_of_frag}")

            # posielanie Special First Header
            header = struct.pack('!hii', SFH_MSG, num_of_frag, 0)
            client_sock.sendto(header, server_ip_port)

            # cakanie na ACK
            data = client_sock.recvfrom(fragment_size)
            flag = struct.unpack_from('!h', data[0])
            if flag[0] == SFH_ACK:
                send_message(num_of_frag, msg)

        elif choice == 'f':
            print("\n--------Sending a FILE--------")
            while 1:
                file_name_in = input("\nFile to send:\n")
                try:
                    with open(f"to sent\\{file_name_in}", 'rb') as f:
                        the_file = f.read()
                    f.close()

                except FileNotFoundError:
                    print("File does not exist")
                else:
                    break

            size = os.path.getsize(f"to sent\\{file_name_in}")
            num_of_frags = math.ceil(size / fragment_size)
            print(f"\nNumber of fragments: {num_of_frags}")
            send_sfh(file_name_in)
            send_file(the_file, num_of_frags)


#....po odoslani spravy/suboru, vyber dalsiej akcie................................................
def next_action():
    print("\n--------End of transfer--------\n\nWould you like to continue or end the connection?")
    m = input("c - for to continue\nx - to end the connection\n\n")
    while not (m == "c" or m == "C" or m == "x" or m == "X"):
        m = input("Try again!\na/c - for to continue\nx - to end the connection\n")
    return m.lower()


#....client main...................................................................................
def client_main():
    global keep_alive_status

    while 1:
        run_client()

        keep_alive_status[0] = True
        t = start_thread(keep_alive_interval)

        choice_f = next_action()
        if choice_f == "c":
            keep_alive_status = [False, UPD_END_CON]
        else:
            keep_alive_status = [False, UPD_END_QUT]

        t.join()
        print("Keep alive turned off\n")

        if choice_f == "c" or choice_f == "a":
            continue
        else:
            client_sock.close()
            print("\n--------Closing a connection with the server--------\n")
            os.system('py main.py')
            break


get_ip_port()
client_main()
