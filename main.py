import os

print("-------------------------------------------------------\n-------------------------------------------------------\n")
choice = input("Choose between server and client or exit the program:\n\nc - for client\ns - for server\nx - exit the program\n")

while 1:
    if choice == "c" or choice == "C":
        print("\n------------------------------------------------")
        os.system('py client.py')
        break
    elif choice == "s" or choice == "S":
        print("\n------------------------------------------------")
        os.system('py server.py')
        break
    elif choice == "x" or choice == "X":
        print("\n-----------------------------End of the program---------------------------------")
        break
    else:
        print("Pick again!")
        choice = input("c - for client\ns - for server\nx - exit the program\n")
