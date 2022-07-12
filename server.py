import socket
import struct
import crcmod
import os


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

#....globalne premenne..............................................................................
HEADER_SIZE = 10

# intervaly
fragment_timeout_interval = 25
fragment_timeout_interval_longer = 60
keep_alive_interval = 11    # +1 sekunda

# input oboch stran
main_address = (0, 0)
port = 0
fragment_size_w_header = 0


#....vytvorenie socketu a funkcia na CRC...........................................................
server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
crcfunc = crcmod.mkCrcFun(0x107, initCrc=0x00, xorOut=0x00)


#....input port a nadviazanie komunikacie..........................................................
def get_port():
    global port, main_address
    try:
        server_sock.settimeout(fragment_timeout_interval_longer)
        print()
        while 1:
            try:
                port = int(input("Input Port: "))
            except ValueError:
                print("It has to be a whole number")
            else:
                break

        # port = 25000
        # print(f"\nInput Port: ... {port}")

        #....bind, server posliela svoj port
        server_sock.bind(("", port))
        empt, main_address = server_sock.recvfrom(1500)
        print(f"\nConnection was established\nIP: {main_address[0]}\nport: {main_address[1]}")

    except socket.timeout:
        print(f"\nFragment didn't arrive in {fragment_timeout_interval_longer} seconds\nExiting the program")
        server_sock.close()
        quit()


#....prijimanie spravy.............................................................................
def receive_message(fragments_to_receive):
    received_msg = []
    print("\n--------Receiving a MESSAGE--------\n")
    try:
        server_sock.settimeout(fragment_timeout_interval)
        while 1:
            # prijatie spravy
            msg_data, addr = server_sock.recvfrom(fragment_size_w_header)
            head = struct.unpack_from('!hii', msg_data[:HEADER_SIZE])
            if head[0] == DATA:
                raw_msg = (msg_data[HEADER_SIZE:]).decode()
                crc_after = crcfunc(raw_msg.encode())
                # kontrola crc
                if head[1] != crc_after:
                    while 1:
                        # chybne crc - zaslanie REP flagu
                        print(f"Fragment number {head[2]} was received -- \nCRC - FAIL")
                        head_to_send = struct.pack('!h', REP)
                        server_sock.sendto(head_to_send, main_address)
                        # prijatie spravy znova
                        msg_data_rep, addr = server_sock.recvfrom(fragment_size_w_header)
                        head = struct.unpack_from('!hii', msg_data_rep[:HEADER_SIZE])
                        raw_msg_rep = (msg_data_rep[HEADER_SIZE:]).decode()
                        crc_after_rep = crcfunc(raw_msg_rep.encode())
                        if head[1] == crc_after_rep:
                            # crc uz ok - zaslanie ACK flagu
                            print(f"Fragment number {head[2]} was received\nCRC - OK")
                            received_msg.insert(head[2], raw_msg_rep)
                            head_to_send = struct.pack('!h', ACK)
                            server_sock.sendto(head_to_send, main_address)
                            break
                else:
                    # crc ok - zaslanie ACK flagu
                    received_msg.insert(head[2], raw_msg)
                    head_to_send = struct.pack('!h', ACK)
                    server_sock.sendto(head_to_send, main_address)
                    print(f"Fragment number {head[2]} was received\nCRC - OK")

                # ak prisli vsetky packety
                if head[2] == fragments_to_receive:
                    whole_msg = "".join(received_msg)
                    return whole_msg

    except socket.timeout:
        print(f"\nFragment didn't arrive in {fragment_timeout_interval} seconds\nExiting the program")
        server_sock.close()
        quit()


#....prijimanie sfh pre subor, kde data su nazov suboru............................................
def get_file_name(frags, crc, fm_data):
    data_to_read = fm_data
    file_name_list = []
    try:
        server_sock.settimeout(fragment_timeout_interval)
        for index in range(frags):
            if index != 0:
                data_to_read, addr = server_sock.recvfrom(fragment_size_w_header)
            file_n = (data_to_read[HEADER_SIZE:]).decode()
            crc_after = crcfunc(file_n.encode())
            if crc_after != crc:
                while 1:
                    # chybne crc - zaslanie REP flagu
                    head_to_send = struct.pack('!h', REP)
                    server_sock.sendto(head_to_send, main_address)
                    # prijatie nazvu znova
                    data_r, addr = server_sock.recvfrom(fragment_size_w_header)
                    head_rep = struct.unpack_from('!hii', data_r[:HEADER_SIZE])
                    file_n = (data_r[HEADER_SIZE:]).decode()
                    crc_after_rep = crcfunc(file_n.encode())
                    if head_rep[2] == crc_after_rep:
                        # crc uz ok
                        file_name_list.insert(index, file_n)
                        head_to_send = struct.pack('!h', SFH_ACK)
                        server_sock.sendto(head_to_send, main_address)
                        break
            else:
                file_name_list.insert(index, file_n)
                head_to_send = struct.pack('!h', SFH_ACK)
                server_sock.sendto(head_to_send, main_address)

    except socket.timeout:
        print(f"\nFragment didn't arrive in {fragment_timeout_interval} seconds\nExiting the program")
        server_sock.close()
        quit()

    whole_file_name = "".join(file_name_list)
    name = whole_file_name.split(".")[0]
    f_format = whole_file_name.split(".")[1]
    return name, f_format


#....prijimanie suboru.............................................................................
def receive_file():
    print("\n--------Receiving a FILE--------\n")
    received_file = []
    try:
        server_sock.settimeout(fragment_timeout_interval)
        # prijatie prveho fragmentu
        file_data, addr = server_sock.recvfrom(fragment_size_w_header)
        head = struct.unpack_from('!hii', file_data[:HEADER_SIZE])
        # na mieste index ma celkovy pocet fragmentov
        fragments_to_receive = head[2]
        index = 1
        count = 0

        while 1:
            count += 1
            # prijatie suboru, ak je to prvy fragment, tak sa preskoci
            if count != 1:
                file_data, addr = server_sock.recvfrom(fragment_size_w_header)
                head = struct.unpack_from('!hii', file_data[:HEADER_SIZE])
                index = head[2]
            if head[0] == DATA:
                raw_file = (file_data[HEADER_SIZE:])
                crc_after = crcfunc(raw_file)
                # kontrola crc
                if head[1] != crc_after:
                    while 1:
                        # chybne crc - zaslanie REP flagu
                        print(f"Fragment number {index} was received -- \nCRC - FAIL")
                        head_to_send = struct.pack('!h', REP)
                        server_sock.sendto(head_to_send, main_address)
                        # prijatie spravy znova
                        file_data_rep, addr = server_sock.recvfrom(fragment_size_w_header)
                        head_rep = struct.unpack_from('!hii', file_data_rep[:HEADER_SIZE])
                        raw_file_rep = (file_data_rep[HEADER_SIZE:])
                        crc_after_rep = crcfunc(raw_file_rep)
                        if head_rep[1] == crc_after_rep:
                            # crc uz ok - zaslanie ACK flagu
                            print(f"Fragment number {head_rep[2]} was received\nCRC - OK")
                            received_file.insert(head_rep[2], raw_file_rep)
                            head_to_send = struct.pack('!h', ACK)
                            server_sock.sendto(head_to_send, main_address)
                            break
                else:
                    # crc ok - zaslanie ACK flagu
                    received_file.insert(index, raw_file)
                    head_to_send = struct.pack('!h', ACK)
                    server_sock.sendto(head_to_send, main_address)
                    print(f"Fragment number {index} was received\nCRC - OK")

                # ak prisli vsetky packety
                if index == fragments_to_receive:
                    whole_file = b''.join(received_file)
                    return whole_file

    except socket.timeout:
        print(f"\nFragment didn't arrive in {fragment_timeout_interval} seconds\nExiting the program")
        server_sock.close()
        quit()


def run_server():
    global fragment_size_w_header
    try:
        server_sock.settimeout(fragment_timeout_interval_longer)
        #....pride nastavena velkost fragmentu.....................................................
        data = server_sock.recvfrom(4)
        info = int(data[0].decode())

        frg_size = info
        fragment_size_w_header = frg_size + HEADER_SIZE
        print("\n--------Fragment--------\n")
        print(f"Fragment size: {frg_size} , ({fragment_size_w_header} with header)")

        #....prijatie Special Firt Header packet...........................................................
        data, address = server_sock.recvfrom(fragment_size_w_header)
        flag, frgs_number, special_crc = struct.unpack('!hii', data[:HEADER_SIZE])

        # Quit
        if flag == FIN:
            server_sock.close()
            print("\n-----------------------------End of the program---------------------------------")
            quit()

        # Message
        elif flag == SFH_MSG:
            header = struct.pack('!h', SFH_ACK)
            server_sock.sendto(header, main_address)
            message = receive_message(frgs_number)
            print(f"\nMessage:\n{message}")

        # File
        elif flag == SFH_FIL:
            file_name, file_format = get_file_name(frgs_number, special_crc, data)
            file = receive_file()
            print(f"\nReceived file: {file_name}.{file_format}\n")
            print("Input absolute path to where you'd like to save this file:")
            while 1:
                path = input("\nPath:\n")
                try:
                    if path[-1:] == "\\":
                        f = open(f'{path}{file_name}.{file_format}', 'wb')
                    else:
                        f = open(f'{path}\\{file_name}.{file_format}', 'wb')
                    f.write(bytearray(file))
                    f.close()
                    print("Done")
                except FileNotFoundError:
                    print("Path does not exist")
                else:
                    break

    except socket.timeout:
        print(f"\nFragment didn't arrive in {fragment_timeout_interval_longer} seconds\nExiting the program")
        server_sock.close()
        quit()


#....po prijati spravy/suboru, vyber dalsiej akcie.................................................
def next_action():
    print("\n--------End of transfer--------\n\nWould you like to continue or end the connection?")
    m = input("c - for to continue\nx - to end the connection\n")
    while not (m == "c" or m == "C" or m == "x" or m == "X"):
        m = input("Try again!\nc - for to continue\nx - to end the connection\n")

    return m.lower()


#....prijimanie keep alive packetov................................................................
def recv_keep_alive():
    flag = ""
    while 1:
        try:
            server_sock.settimeout(keep_alive_interval)
            data = server_sock.recvfrom(HEADER_SIZE)
            flag = struct.unpack_from('!h', data[0])
        except socket.timeout:
            print(f"\nKeep alive packet didn't arrive in {keep_alive_interval} seconds\nExiting the program")
            server_sock.close()
            quit()

        if flag[0] == UPD:
            continue
        elif flag[0] == UPD_END_CON:
            flag = "c"
            break
        elif flag[0] == UPD_END_QUT:
            flag = "x"
            break
    return flag


#....server main...................................................................................
def server_main():
    while 1:
        run_server()
        choice_f = recv_keep_alive()
        # choice_f = next_action()
        if choice_f == "c":
            continue
        else:
            server_sock.close()
            print("\n--------Closing a connection with the client--------\n")
            os.system('py main.py')
            break


get_port()
server_main()
