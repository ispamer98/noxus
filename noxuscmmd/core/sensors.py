class Sensors:
    @staticmethod
    def get_cpu_temp() -> float:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_milli = int(f.read().strip())
            return temp_milli / 1000.0
        except:
            return 0.0