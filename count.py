import rospy
from turtlebro import TurtleBro
import math
import cv2
import numpy
import random


h=700
w=700
array=numpy.zeros((h, w, 3), dtype=numpy.uint8)

cv2.circle(array, (w//2, h//2), 14, (255,255,255), -1)
array[h//2][w//2]=[255,255,255]

def get_cords(d, a):
    return (math.cos(math.radians(a))*d, math.sin(math.radians(a))*d)


def count_points(distances, x_zone_start, x_zone_end, y_zone_start, y_zone_end, min_distance):
    points=[]
    clusters=[]
    for i in range(len(distances)):
        if distances[i] != 0:
            if x_zone_start<get_cords(distances[i], i)[0]<x_zone_end and y_zone_start<get_cords(distances[i], i)[1]<y_zone_end:
                points.append(get_cords(distances[i], i))
    while points:
        clusters.append([points.pop(0)])



        for current in clusters[-1]:
            result=1
            while result:
                result=0
                for point in points:
                    if ((current[0]-point[0])**2+(current[1]-point[1])**2)<=min_distance**2:
                        clusters[-1].append(point)
                        result+=1
                for i in range(len(clusters[-1])):
                    if clusters[-1][i] in points:
                        points.remove(clusters[-1][i])
        
    return clusters



if __name__ == '__main__':
    try:
        robot = TurtleBro()
        rospy.loginfo("TurtleBro initialized")
        robot.wait(1)

        x, y, theta = robot.pose
        rospy.loginfo(f"Position: x={x:.2f}, y={y:.2f}, angle={theta:.1f}")

        d = robot.distance(360)
        # for i in range(len(d)):
        #     if d[i] != 0:
        #         print(i, get_cords(d[i], i))
        result=count_points(robot.distance(360), 0, 1, -1, 1, 0.05)
        print(len(result))
        for i in range(len(result)):
            color=[random.randint(50,255), random.randint(50,255), random.randint(50,255)]
            for point in result[i]:
                array[-int(point[0]*100)+w//2][-int(point[1]*100)+h//2][0]=color[0]
                array[-int(point[0]*100)+w//2][-int(point[1]*100)+h//2][1]=color[1]
                array[-int(point[0]*100)+w//2][-int(point[1]*100)+h//2][2]=color[2]
            # print(result[i])

        
        cv2.imwrite('result.png', array)


        robot.close()
    except rospy.ROSInterruptException:
        pass
