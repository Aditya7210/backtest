# Docker Hand-Holding Guide for Algo Trading System

Welcome to the comprehensive Docker guide for this project! This will cover everything from launching your environment to executing Streamlit without holding your terminal hostage. 

> **Important Concept:** In this project, your container is named `algo_trading_app` via the `docker-compose.yml` file. When interacting with docker, we will use this name. 
> 
> Also, inside the container, your Windows project folder (`C:\Users\aggar\PROJECTS\Algo_Trading_System`) is mounted to `/app`. So, inside Docker, all file paths start with `/app`.

---

## 1. Docker Compose: The Easiest Way to Start
Your project comes with a `docker-compose.yml` file, which is pre-configured to set up your whole environment and mount your files so changes sync automatically.

### Start the entire environment (Background mode)
The `-d` flag stands for **detached**. This starts your container in the background, freeing up your terminal for other commands!
```bash
docker compose up -d
```
*(Note: Use `docker-compose` (with a hyphen) if you have an older version of Docker, but `docker compose` is the modern standard).*

### Start + auto-open dashboard in browser
If you want the browser to open automatically after startup:
- PowerShell (Windows):
```powershell
.\compose-up.ps1
```
- Bash/zsh (macOS/Linux):
```bash
./compose-up.sh
```
These wrappers run `docker compose up -d`, wait for Streamlit health, and then open `http://localhost:8501`.

### Stop and Shutdown the environment
Ready to shut down for the day? This will smoothly stop and remove the container.
```bash
docker compose down
```

### Rebuild the environment
If you add new libraries to your `requirements.txt` or change the `Dockerfile`, you need to tell compose to rebuild:
```bash
docker compose up -d --build
```

---

## 2. Running Python Scripts & Streamlit Inside the Container
Once your container (`algo_trading_app`) is running (via the `up -d` command), you can execute commands *inside* it using `docker exec`.

> **CRITICAL RULE**: Do not use Windows paths (like `C:\Users\...`) inside `docker exec`. Use the relative path of the file as it exists in your project folder!

### How to run the Streamlit Dashboard
Good news! Your `docker-compose.yml` has been configured to **automatically start Streamlit** the moment you start your container.

You don't need to manually run any `docker exec` commands for Streamlit anymore. Just start your environment normally:
```bash
docker compose up -d
```
Then, go directly to your browser and open **http://localhost:8501** to view the dashboard!

### How to stop or restart the Streamlit Dashboard
Since Streamlit is now the default background command tied to the container's lifecycle:
- **To stop it:** Simply stop the whole container using `docker compose down` or `docker stop algo_trading_app`.
- **To restart it:** (For example, if it crashes or you want a completely fresh slate), just run:
```bash
docker compose restart
```

### How to run the Algorithm Testing Engine
Now that you have a master execution engine, you can run all your backtests through it by simply executing:
```bash
docker exec algo_trading_app python Backtesting/execution_engine.py
```
*(Remember to modify the `DATA_FILE`, `STRATEGY_FILE`, and `STRATEGY_CLASS` config variables inside that file before running!)*


### How to run a Data Download Script
Similar to the testing script, just point to the correct python file inside your project (`/app`):
```bash
docker exec algo_trading_app python Data/download_script.py
```

### How to magically open the terminal INSIDE the container
If you want to dive into the Linux terminal of the container and run multiple commands manually:
```bash
docker exec -it algo_trading_app bash
# or if bash isn't available:
docker exec -it algo_trading_app sh
```
When inside, you can run `python main.py` or `ls` normally as if you were on a Linux server. Type `exit` to get out.

---

## 3. Managing Docker Images (The Blueprints)
Docker **Images** are the blueprints used to create containers.

### Create/Build an image from your Dockerfile
If you want to manually build an image (instead of using `docker compose`), you can do so and give it a custom name (`-t`). The `.` at the end means "use the Dockerfile in the current directory".
```bash
docker build -t my_custom_image .
```

### Rename (Tag) an image
You can't technically "rename" an image, but you can create a new tag pointing to the exact same image. Let's rename `my_custom_image` to `prod_algo_image`:
```bash
docker image tag my_custom_image prod_algo_image
```
*Optional: You can then delete the old tag using `docker rmi my_custom_image` .*

### List all your images
```bash
docker images
```

---

## 4. Managing Docker Containers (The Running Apps)
A **Container** is a live, running instance of an Image.

### Launch a standalone container
If you don't want to use `docker compose` and want to manually spin up a container from your image:
```bash
docker run -d --name custom_algo_container my_custom_image
```

### Check what containers are currently running
```bash
docker ps
```
To see ALL containers (even the stopped/crashed ones), use:
```bash
docker ps -a
```

### Rename a running (or stopped) container
Want to change a container's name from `custom_algo_container` to `backtesting_container`?
```bash
docker rename custom_algo_container backtesting_container
```

### Stop a specific container manually
```bash
docker stop algo_trading_app
```

### Remove/Delete a container permanently
*(You must stop the container first before removing it).*
```bash
docker rm algo_trading_app
```
*(If you want to forcibly remove a running container immediately, use `docker rm -f algo_trading_app`).*

---

## 5. Useful Debugging & Maintenance

### View live logs of your container
If your code crashes or you want to see standard print statements from background tasks:
```bash
docker logs algo_trading_app
```
To "follow" the logs live as they are generated (similar to watching terminal output in real-time):
```bash
docker logs -f algo_trading_app
```
*(Press `Ctrl+C` to stop following the logs).*

### Clean up space! (System Prune)
Docker can consume gigabytes of storage over time. This command cleans up all stopped containers, unused networks, and dangling images. 
```bash
docker system prune
```
*(If you also want to wipe out absolutely all unused images and builder cache, run `docker system prune -a --volumes`).*
