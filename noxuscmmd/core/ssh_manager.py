import paramiko

class SSHManager:
    @staticmethod
    def execute(command: str, host: str, user: str) -> str:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # Al no pasar password, usa autenticación por Key
            client.connect(hostname=host, username=user, timeout=10)
            
            _, stdout, stderr = client.exec_command(command)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            
            client.close()
            return out if not err else f"Error: {err}"
        except Exception as e:
            return f"Excepción SSH: {str(e)}"