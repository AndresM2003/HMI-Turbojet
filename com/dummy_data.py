# com/dummy_data.py

import random
import math
from PyQt6.QtCore import QThread, pyqtSignal
import time


class DummyDataThread(QThread):
    data_updated = pyqtSignal(dict)

    def run(self):
        rpm = 20000
        t   = 0

        while True:
            t   += 0.1
            rpm += random.uniform(-500, 800)
            rpm  = max(0, rpm)

            data = {
                # --- Variables originales ---
                "rpm":       rpm,
                "egt":       random.uniform(400, 750),
                "fuel_flow": random.uniform(10, 30),
                "pressure":  random.uniform(1.5, 3.5),

                # --- Main system ---
                "intake_temp":     random.uniform(25, 50),
                "intake_pressure": random.uniform(0.9, 2.2),
                "intake_flow":     random.uniform(0.4, 1.1),
                "comb_temp":       random.uniform(500, 820),
                "comb_pressure":   random.uniform(1.5, 4.2),
                "turbine_inlet":   random.uniform(600, 880),
                "turbine_outlet":  random.uniform(400, 760),
                "turbo_rpm":       rpm * 3.2 + random.uniform(-1000, 1000),
                "boost_pressure":  random.uniform(1.2, 3.0),
                "exhaust_temp":    random.uniform(300, 640),

                # --- Fuel system ---
                "tank_pressure":   random.uniform(4.0, 9.0),
                "tank_level":      max(0, 80 - t * 0.05 + random.uniform(-1, 1)),
                "fuel_pressure":   random.uniform(2.0, 5.0),
                "fuel_temp":       random.uniform(15, 50),
                "valve_position":  random.uniform(30, 85),
                "regulator_press": random.uniform(1.5, 3.5),

                # --- Lubrication ---
                "oil_pressure":    random.uniform(2.0, 5.5),
                "oil_temp":        random.uniform(50, 105),
                "oil_flow":        random.uniform(3.0, 8.5),
                "oil_level":       max(0, 70 - t * 0.02 + random.uniform(-0.5, 0.5)),
                "pump_rpm":        random.uniform(1200, 2600),
                "oil_inlet_temp":  random.uniform(40, 70),
                "oil_outlet_temp": random.uniform(70, 105),
                "filter_dp":       random.uniform(0.1, 0.7),
            }

            self.data_updated.emit(data)
            time.sleep(0.1)