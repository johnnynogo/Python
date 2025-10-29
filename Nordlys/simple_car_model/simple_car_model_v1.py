import numpy as np
import matplotlib.pyplot as plt

class Car:
    def __init__(self, speed):
        self.speed = 0

    def reset_speed(self):
        self.speed = 0
        
    def set_speed(self, speed):
        self.speed = speed
        
    def get_speed(self):
        return self.speed
        
    def accelerate(self, speed):
        self.speed += speed
        print(f"Current speed: {self.get_speed()} \n")
            
    def brake(self, speed):
        self.speed -= speed
        print(f"Current speed: {self.get_speed()} \n")
  
def main():
    initial_speed = 0
    car = Car(initial_speed)

    car.accelerate(1)

    while car.get_speed() != 0:
        accelerate_or_brake = input("Enter 1 to accelerate. Enter 0 to brake: ")

        if int(accelerate_or_brake) == 1:
            accelerate_input = input("Type in a number you want to add to speed: ")
            car.accelerate(int(accelerate_input))
        elif int(accelerate_or_brake) == 0:
            brake_input = input("Type in a number you want to subtract to speed: ")
            car.brake(int(brake_input))

main()