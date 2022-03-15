import argparse
import random

from pynfra.modules.classes import RecipeBase


UNATTENDED_UPGRADES_CFG = """
Unattended-Upgrade::Origins-Pattern {
    "origin=Debian,codename=${distro_codename},label=Debian-Security";
    "origin=TorProject";
};
Unattended-Upgrade::Package-Blacklist {
};
Unattended-Upgrade::Automatic-Reboot "true";
"""


UNATTENDED_AUTO_CFG = """
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::AutocleanInterval "5";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Verbose "1";
"""


TOR_SOURCES_LIST = """
deb     [signed-by=/usr/share/keyrings/tor-archive-keyring.gpg] https://deb.torproject.org/torproject.org ###DISTRIBUTION### main
deb-src [signed-by=/usr/share/keyrings/tor-archive-keyring.gpg] https://deb.torproject.org/torproject.org ###DISTRIBUTION### main
"""


CONFIG_TORRC = """
BridgeRelay 1

# Replace "TODO1" with a Tor port of your choice.
# This port must be externally reachable.
# Avoid port 9001 because it's commonly associated with Tor and censors may be scanning the Internet for this port.
ORPort ###TODO1###

ServerTransportPlugin obfs4 exec /usr/bin/obfs4proxy

# Replace "TODO2" with an obfs4 port of your choice.
# This port must be externally reachable and must be different from the one specified for ORPort.
# Avoid port 9001 because it's commonly associated with Tor and censors may be scanning the Internet for this port.
ServerTransportListenAddr obfs4 0.0.0.0:###TODO2###

# Local communication port between Tor and obfs4.  Always set this to "auto".
# "Ext" means "extended", not "external".  Don't try to set a specific port number, nor listen on 0.0.0.0.
ExtORPort auto

# Replace "<address@email.com>" with your email address so we can contact you if there are problems with your bridge.
# This is optional but encouraged.
ContactInfo <###CONTACTINFO###>

# Pick a nickname that you like for your bridge.  This is optional.
#Nickname ###NICKNAME###
"""


class Debian11Bridge(RecipeBase):
    def __init__(self, node):
        self.env = {
            "DEBIAN_FRONTEND": "noninteractive"
        }
        super().__init__(node, self.env)

    def main(self, args_raw):
        self.__parser = argparse.ArgumentParser()
        subparsers = self.__parser.add_subparsers()
        self.__parser.set_defaults(func=self.__parser.print_help)

        parser_run = subparsers.add_parser('run', help='run contactinfo orport obs4port')
        parser_run.add_argument('contactinfo', type=str, help='contact info (email)')
        parser_run.add_argument('orport', type=int, help='orport')
        parser_run.add_argument('obs4port', type=int, help='obs4port')
        parser_run.set_defaults(func='run')

        parser_status = subparsers.add_parser('status', help='status: print status')
        parser_status.set_defaults(func='status')

        args = self.__parser.parse_args(*args_raw)

        func = args.func
        if func == "run":
            self.__do_main(args.contactinfo, args.orport, args.obs4port)
        elif func == "status":
            self.__do_status()
        else:
            self.__parser.print_help()

    def __do_status(self):
        print("[+] Calling \"whoami\"")
        self.run("whoami")

    def __do_main(self, contactinfo, orport, obs4port):
        print("[+] Spray verifying versions")
        version, codename = self.get_osrelease()
        arch = self.get_arch()

        if version != "Debian GNU/Linux" or codename != "bullseye":
            print("ERROR This Distribution/version is unsupported: version: {}, codename: {}".format(version, codename))
            exit(1)

        if arch not in ("amd64",):
            print("ERROR This architecture is not supported: {}".format(arch))
            exit(1)

        print("\tversion: {}\n\tcodename: {}\n\tarch: {}".format(version, codename, arch))

        # Based on: https://community.torproject.org/relay/setup/guard/debian-ubuntu/updates/
        print("[+] Spray enabling updates")
        self.run("apt-get update")
        self.run("apt-get upgrade -y")
        self.run("apt-get install -y unattended-upgrades apt-listchanges")

        self.writeconfig("/etc/apt/apt.conf.d/50unattended-upgrades", UNATTENDED_UPGRADES_CFG)
        self.writeconfig("/etc/apt/apt.conf.d/20auto-upgrades", UNATTENDED_AUTO_CFG)
        # self.run(conn, "unattended-upgrade --debug --dry-run")

        # Based on: https://support.torproject.org/apt/tor-deb-repo/
        print("[+] Spray configuring tor repo")
        self.run("apt-get install -y apt-transport-https gpg")

        self.writeconfig("/etc/apt/sources.list.d/tor.list", TOR_SOURCES_LIST,
                         {
                             "###DISTRIBUTION###": codename
                         })

        self.run("wget -qO- https://deb.torproject.org/torproject.org/A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89.asc | gpg --dearmor | tee /usr/share/keyrings/tor-archive-keyring.gpg >/dev/null")

        self.run("apt-get update")
        self.run("apt-get install -y tor deb.torproject.org-keyring")

        # Based on: https://community.torproject.org/relay/setup/bridge/debian-ubuntu/
        print("[+] Spray installing packages")
        self.run("apt-get update")
        self.run("apt-get install -y tor")
        self.run("apt-get install -y obfs4proxy")

        self.writeconfig("/etc/tor/torrc", CONFIG_TORRC,
                         {
                            "###TODO1###": str(random.randint(*(orport, orport))),
                            "###TODO2###": str(random.randint(*(obs4port, obs4port))),
                            "###CONTACTINFO###": contactinfo,
                            # TODO: support this in the future
                            # ("###NICKNAME###", nickname),
                         })

        self.run("setcap cap_net_bind_service=+ep /usr/bin/obfs4proxy")

        for filename in ["/lib/systemd/system/tor@default.service",
                         "/lib/systemd/system/tor@.service"]:
            self.editconfig(filename, "NoNewPrivileges=yes", "NoNewPrivileges=no")

        self.run("systemctl daemon-reload")

        self.run("systemctl enable --now tor.service")
        self.run("systemctl restart tor.service")

        # test, check logs:
        # TODO
        # self.run(conn, "journalctl -e -u tor@default | grep \"Self-testing indicates\"")
