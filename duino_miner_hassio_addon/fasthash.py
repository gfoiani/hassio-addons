import os
from pathlib import Path
import requests
from platform import machine, system, python_version, python_version_tuple

class Fasthash:
    base_url = 'https://server.duinocoin.com/fasthash'

    @staticmethod
    def init():
        try:
            import libducohasher
            print("Fasthash available")
        except Exception as e:
            python_version_minor = int(python_version_tuple()[1])
            message = (
                f"Your Python version is too old ({python_version()}).\n"
                if python_version_minor <= 6 else
                "Fasthash accelerations are not available for your OS.\n"
                f"If you wish to compile them for your system, visit:\n"
                "https://github.com/revoxhere/duino-coin/wiki/How-to-compile-fasthash-accelerations\n"
                f"(Libducohash couldn't be loaded: {str(e)})"
            )
            print(message.replace("\n", "\n\t\t"), 'warning', 'sys0')

    @staticmethod
    def load():
        if system() == 'Windows':
            library_name = "libducohasher.pyd"
            url = f"{Fasthash.base_url}/libducohashWindows.pyd"
        elif system() == 'Linux':
            processor_mapping = {
                "aarch64": "libducohashPi4.so",
                "armv7l": "libducohashPi4_32.so",
                "armv6l": "libducohashPiZero.so",
                "x86_64": "libducohashLinux.so"
            }
            processor = machine()
            print(f"processor: {processor}")
            library_name = processor_mapping.get(processor, None)
            url = f'{Fasthash.base_url}/{library_name}' if library_name else None
        elif system() == 'Darwin':
          library_name = 'libducohasher.so'
        else:
          library_name = None

        if library_name and not Path(library_name).is_file():
          print("Downloading fasthash")
          r = requests.get(url, timeout=5)
          with open('libducohasher.so', 'wb') as f:
            f.write(r.content)
