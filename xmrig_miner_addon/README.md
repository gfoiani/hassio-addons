# XMRig miner Home Assistant addon
_____
- XMRig miner runs in docker as a HASSIO addon
- Supported architectures:
  - amd64

 ## Installation
 1. Add a repository via MY button

   [![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgfoiani%2Fhassio-addons%2F)

 2. Install this add-on. (It will take about 20 minutes or more. )
 3. Configure this add-on.
 4. Start the addon and check the logs if any errors.
 5. Enjoy mining!
 ## Configuration options:
 1.  ```mining_pool``` - URL of mining server.
 2. ```wallet``` - Username or wallet adress for mining server.
 3. ```password``` - Password for mining server. Default is ```x```
 4. ```threads``` - Number of CPU threads.

