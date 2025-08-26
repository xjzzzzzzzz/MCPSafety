import os
def alert_user(msg):
    # Directly injecting user input into a shell command
    os.system(f"echo {msg}")
if __name__ == "__main__":
    alert_user("MSFT price is above $300;echo $PATH")