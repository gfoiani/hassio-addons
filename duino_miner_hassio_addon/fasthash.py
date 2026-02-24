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
        url = None
        library_name = None

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
            # No pre-built macOS binary is available from duinocoin.com;
            # skip download and fall back to pure-Python hashing.
            print("Fasthash: no pre-built macOS binary available, using pure-Python fallback")
            return
        # else: unknown OS → library_name and url stay None

        MODULE_NAME = "libducohasher.so"

        if library_name and not Path(MODULE_NAME).is_file():
            if url is None:
                print(f"Fasthash: no download URL for {system()} {machine()}, using pure-Python fallback")
                return
            print("Downloading fasthash")
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                with open(MODULE_NAME, 'wb') as f:
                    f.write(r.content)
                print(f"Fasthash downloaded: {library_name} -> {MODULE_NAME}")
            except Exception as e:
                print(f"Fasthash download failed: {e} — using pure-Python fallback")
