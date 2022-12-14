from __future__ import print_function

import collections
import random

import Pyro4
import os
import sys
import aes
import pandas as pd
from threading import Thread

MASTER_IP = "10.0.0.125"
NS_IP = "10.0.0.125"
MASTER_PORT = 9091

sys.excepthook = Pyro4.util.excepthook

@Pyro4.expose
@Pyro4.behavior(instance_mode="single")
class MasterServer(object):
    def __init__(self):
        self.replica = 3
        self.registered_users = set()
        self.file_data = collections.defaultdict(set)
        self.read_permissions = collections.defaultdict(set)
        self.write_permissions = collections.defaultdict(set)
        self.delete_permissions = collections.defaultdict(set)
        self.file_deleted = {}
        self.file_keys = {}

        # update the all users
        self.all_users = {}
        with open("validation.csv") as f:
            lines = f.readlines()
            for line in lines:
                username, password = line.split(",")
                self.all_users[username.strip()] = password.strip()
        print(self.all_users)

    def validate_user(self, username, password):
        if username not in self.all_users :
            return False
        if password != self.all_users[username]:
            return False
        return True

    def register_user(self, user_ip):
        self.registered_users.add(user_ip)
        return True

    def random_user_ips(self):
        if len(self.registered_users) <= self.replica:
            return self.registered_users
        users = []
        reg_users = list(self.registered_users)
        idx = 0
        while idx < self.replica:
            rand = random.choice(reg_users)
            reg_users.remove(rand)
            users.append(rand)
            idx += 1
        return users

    def create(self, file_name, user_ip):
        users = self.random_user_ips()
        for user in users:
            self.file_data[file_name].add(user)
            self.read_permissions[file_name].add(user_ip)
            self.write_permissions[file_name].add(user_ip)
            self.delete_permissions[file_name].add(user_ip)
        self.file_deleted[file_name] = False
        key = aes.getKey(aes.generate_random_string())
        self.file_keys[file_name] = key
        print(key)
        return users, key

    def read(self, name, user_ip):
        if (name in self.file_deleted and self.file_deleted[name]) or \
                name not in self.file_deleted:
            return "file doesn't exist", None
        if user_ip not in self.read_permissions[name]:
            return "you do not have read permission", None
        users = list(self.file_data[name])
        key = self.file_keys[name]
        return users[0], key

    def write(self, name, user_ip):
        if (name in self.file_deleted and self.file_deleted[name]) or \
                name not in self.file_deleted:
            return "file doesn't exist", None
        if user_ip not in self.write_permissions[name]:
            return "you do not have write permission", None
        users = list(self.file_data[name])
        key = self.file_keys[name]
        return users, key

    def delete(self, name, user_ip):
        if (name in self.file_deleted and self.file_deleted[name]) or \
                name not in self.file_deleted:
            return "file doesn't exist", None
        if user_ip not in self.delete_permissions[name]:
            return "you do not have delete/restore permission", None

        self.file_deleted[name] = True

    def restore(self, name, user_ip):
        if (name in self.file_deleted and not self.file_deleted[name]) or \
                name not in self.file_deleted:
            return "file doesn't exist"
        if user_ip not in self.delete_permissions[name]:
            return "you do not have delete/restore permission"

        self.file_deleted[name] = False

    def delegate(self, name, user_ip, other_ip, permission):
        if (name in self.file_deleted and self.file_deleted[name]) or \
                name not in self.file_deleted:
            return "file doesn't exist"
        if permission == "read":
            if user_ip not in self.read_permissions[name]:
                return "current user doesn't have read permission"
            if other_ip in self.read_permissions[name]:
                return "other user already have read permission"
            self.read_permissions[name].add(other_ip)
            return "successfully given read permission"
        if permission == "write":
            if user_ip not in self.write_permissions[name]:
                return "current user doesn't have write permission"
            if other_ip in self.write_permissions[name]:
                return "other user already have write permission"
            self.write_permissions[name].add(other_ip)
            return "successfully given write permission"
        if permission == "delete":
            if user_ip not in self.delete_permissions[name]:
                return "current user doesn't have delete permission"
            if other_ip in self.delete_permissions[name]:
                return "other user already have delete permission"
            self.delete_permissions[name].add(other_ip)
            return "successfully given delete permission"
        return "Invalid permission"

    def malicious_check(self):
        def run():
            file_data = self.file_data
            for file, peers in file_data.items():
                for peer in peers:
                    objs = []
                    with Pyro4.locateNS(host=NS_IP) as ns:
                        for obj, obj_uri in ns.list(prefix="peer.server").items():
                            print("found ", obj)
                            objs.append(Pyro4.Proxy(obj_uri))
                    peerobj = objs[0]
                    key = self.file_keys[file]
                    data = peer.read(aes.encrypt(file, key))
                    if data == "file doesn't exist":
                        print("Malicious Activity detected")
                        print("Exiting out of File distributed system")
                        exit()
        new_thread = Thread(target=run)
        new_thread.start()


def main():
    server_obj = MasterServer()
    server_obj.malicious_check()
    with Pyro4.Daemon(host=MASTER_IP, port=MASTER_PORT) as daemon:
        obj_uri = daemon.register(server_obj)
        with Pyro4.locateNS() as ns:
            ns.register("master.server", obj_uri)
        print("Master Server now available")
        daemon.requestLoop()


if __name__ == "__main__":
    main()
