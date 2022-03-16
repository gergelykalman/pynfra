from pynfra.pynfra import Pynfra

from pynfra.recipes.debian_11_torbridge_install import Debian11Bridge


def main():
    pynfra = Pynfra()
    pynfra.load_recipe("Debian11Bridge", Debian11Bridge)
    pynfra.main()


if __name__ == "__main__":
    main()
