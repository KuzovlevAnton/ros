#!/usr/bin/env python
# -*- coding: utf-8 -*-

import rospy
import math
import time
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from tf.transformations import euler_from_quaternion

# Заглушки для неиспользуемых аппаратных возможностей (светодиоды, камера, звук)


class Utility:
    """Вспомогательный класс для сенсоров и обратной связи (совместимость с API)."""

    def __init__(self, bot):
        self.bot = bot
        self.scan = None
        # Для регистрации callback'ов на кнопки (не реализовано)
        self.names_of_func_to_call = {}
        self.args_of_func_to_call = {}
        self.kwargs_of_func_to_call = {}

    def distance(self, angle):
        return self.bot.distance(angle)

    def wait(self, duration):
        self.bot.wait(duration)

    def call(self, name, button=28, *args, **kwargs):
        pass  # заглушка

    def color(self, col):
        rospy.loginfo(f"[Utility] LED color '{col}' ignored")

    def backlight_all(self, color):
        rospy.loginfo("[Utility] backlight_all ignored")

    def backlight_array(self, colors, fill=None):
        rospy.loginfo("[Utility] backlight_array ignored")

    def photo(self, save, name):
        rospy.logwarn("[Utility] photo not implemented")
        return None

    def say(self, text, voice='', rate=0, language='ru', punctuation_mode='SOME'):
        rospy.logwarn(f"[Utility] say not implemented: {text}")
        return ""

    def play(self, filename, blocking=False, device=''):
        rospy.logwarn(f"[Utility] play not implemented: {filename}")
        return ""

    def close(self):
        pass


class TurtleBro:
    """
    Класс управления роботом TurtleBro (ROS1).
    Полностью повторяет публичный API библиотеки turtlebro_py,
    но реализует движение синхронно через одометрию и прямые команды скорости.
    """

    def __init__(self, node_name='tb_py'):
        # Инициализация ROS-узла, если ещё не сделано
        if not rospy.get_node_uri():
            rospy.init_node(node_name, anonymous=True)

        # Публикатор команд скорости
        self.vel_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)

        # Переменные для хранения последних показаний сенсоров
        self.odom = None
        self.scan = None
        self.odom_has_started = False
        self.init_position_on_start = None  # для вычисления относительных координат

        # Параметры скорости по умолчанию (как в оригинале)
        self.linear_x_val = 0.09      # м/с
        self.angular_z_val = 0.9      # градусы/с (в оригинале так и используется)

        # Тайм-аут для действий (для совместимости, не используется)
        self._action_timeout = 30.0

        # Подписка на топики
        rospy.Subscriber('/odom', Odometry, self._odom_callback)
        rospy.Subscriber('/scan', LaserScan, self._scan_callback)

        # Ожидание первого сообщения одометрии
        self.wait_for_odom_to_start()

        # Вспомогательный объект Utility (обязателен для совместимости)
        self.u = Utility(self)

        # Для привязки функций к кнопкам (заглушка)
        self.names_of_func_to_call = {}
        self.args_of_func_to_call = {}
        self.kwargs_of_func_to_call = {}

        # Частота управления для циклов движения
        self.rate = rospy.Rate(50)

        rospy.on_shutdown(self.close)

    # ---------- Callback'и ----------
    def _odom_callback(self, msg):
        self.odom = msg
        if not self.odom_has_started:
            self.odom_has_started = True
            self.init_position_on_start = msg

    def _scan_callback(self, msg):
        self.scan = msg

    # ---------- Ожидание готовности ----------
    def wait_for_odom_to_start(self, timeout=5.0):
        """Дождаться первого сообщения одометрии."""
        start = rospy.Time.now()
        while not self.odom_has_started and not rospy.is_shutdown():
            if (rospy.Time.now() - start).to_sec() > timeout:
                rospy.logwarn("Timeout waiting for odometry")
                break
            rospy.sleep(0.1)
        if self.odom_has_started:
            rospy.loginfo("Odometry received")

    # ---------- Публичные команды движения ----------
    def forward(self, meters):
        """Движение вперёд на заданное расстояние (метры)."""
        if not isinstance(meters, (int, float)) or meters <= 0:
            rospy.logerr('forward: distance must be positive')
            return False
        try:
            self.__move(meters)
            return True
        except Exception as e:
            rospy.logerr(f'forward failed: {e}')
            return False

    def backward(self, meters):
        """Движение назад на заданное расстояние (метры)."""
        if not isinstance(meters, (int, float)) or meters <= 0:
            rospy.logerr('backward: distance must be positive')
            return False
        try:
            self.__move(-meters)
            return True
        except Exception as e:
            rospy.logerr(f'backward failed: {e}')
            return False

    def right(self, degrees):
        """Поворот направо на заданное количество градусов."""
        if not isinstance(degrees, (int, float)) or degrees <= 0:
            rospy.logerr('right: angle must be positive')
            return False
        try:
            self.__turn(-degrees)
            return True
        except Exception as e:
            rospy.logerr(f'right failed: {e}')
            return False

    def left(self, degrees):
        """Поворот налево на заданное количество градусов."""
        if not isinstance(degrees, (int, float)) or degrees <= 0:
            rospy.logerr('left: angle must be positive')
            return False
        try:
            self.__turn(degrees)
            return True
        except Exception as e:
            rospy.logerr(f'left failed: {e}')
            return False

    def goto(self, x, y, theta=0):
        """
        Перемещение в точку (x, y) в глобальной системе координат,
        после чего поворот на угол theta (градусы).
        """
        try:
            self.__goto(x, y, theta)
            return True
        except Exception as e:
            rospy.logerr(f'goto failed: {e}')
            return False

    # ---------- Приватные методы движения ----------
    def __move(self, meters):
        """
        Линейное движение на расстояние meters (может быть отрицательным).
        Использует self.linear_x_val как модуль скорости.
        """
        if self.odom is None:
            raise RuntimeError("No odometry data")

        # Начальная позиция
        start_x = self.odom.pose.pose.position.x
        start_y = self.odom.pose.pose.position.y

        twist = Twist()
        twist.linear.x = self.linear_x_val if meters > 0 else -self.linear_x_val

        traveled = 0.0
        while not rospy.is_shutdown():
            if self.odom is None:
                break
            dx = self.odom.pose.pose.position.x - start_x
            dy = self.odom.pose.pose.position.y - start_y
            traveled = math.hypot(dx, dy)
            if traveled >= abs(meters):
                break
            self.vel_pub.publish(twist)
            self.rate.sleep()

        self.stop()

    def __turn(self, degrees):
        """
        Поворот на угол degrees (градусы). Положительное значение — против часовой,
        отрицательное — по часовой. Использует self.angular_z_val как модуль скорости (градусы/с).
        """
        if self.odom is None:
            raise RuntimeError("No odometry data")

        if abs(degrees) < 0.1:
            return

        target_angle_rad = math.radians(degrees)
        start_yaw = self._get_yaw()
        target_yaw = self._normalize_angle(start_yaw + target_angle_rad)

        twist = Twist()
        # angular_z_val хранится в градусах/с, переводим в рад/с
        speed_rad = math.radians(abs(self.angular_z_val))
        twist.angular.z = speed_rad if degrees > 0 else -speed_rad

        while not rospy.is_shutdown():
            if self.odom is None:
                break
            current_yaw = self._get_yaw()
            error = self._normalize_angle(current_yaw - target_yaw)
            if abs(error) < math.radians(1.0):  # точность 1 градус
                break
            self.vel_pub.publish(twist)
            self.rate.sleep()

        self.stop()

    def __goto(self, x, y, theta):
        """Внутренняя реализация goto."""
        if self.odom is None:
            raise RuntimeError("No odometry data")

        # Текущая позиция относительно старта
        robot_x, robot_y = self.get_position()
        dx = x - robot_x
        dy = y - robot_y
        distance = math.hypot(dx, dy)

        if distance > 0.01:
            # Угол до цели
            target_angle_rad = math.atan2(dy, dx)
            current_yaw = self._get_yaw()
            angle_diff = self._normalize_angle(target_angle_rad - current_yaw)
            angle_diff_deg = math.degrees(angle_diff)

            # Поворот к цели
            if abs(angle_diff_deg) > 1.0:
                self.__turn(angle_diff_deg)

            # Движение вперёд
            self.__move(distance)

        # Финальный поворот на theta
        if abs(theta) > 1.0:
            self.__turn(theta)

    # ---------- Свойства ----------
    @property
    def pose(self):
        """Возвращает (x, y, yaw) относительно начальной позиции, yaw в градусах."""
        x, y = self.get_position()
        yaw_deg = math.degrees(self._get_yaw())
        return x, y, yaw_deg

    def get_position(self):
        """Возвращает (x, y) относительно начальной позиции."""
        if self.odom is None or self.init_position_on_start is None:
            return (0.0, 0.0)
        x = self.odom.pose.pose.position.x - self.init_position_on_start.pose.pose.position.x
        y = self.odom.pose.pose.position.y - self.init_position_on_start.pose.pose.position.y
        return x, y

    def _get_yaw(self):
        """Текущий угол рыскания в радианах."""
        if self.odom is None:
            return 0.0
        q = self.odom.pose.pose.orientation
        _, _, yaw = euler_from_quaternion([q.x, q.y, q.z, q.w])
        return yaw

    # ---------- Вспомогательные методы ----------
    @staticmethod
    def _normalize_angle(angle):
        """Нормализация угла в [-π, π]."""
        return math.atan2(math.sin(angle), math.cos(angle))

    def stop(self):
        """Остановка робота."""
        self.vel_pub.publish(Twist())

    def close(self):
        """Остановка и освобождение ресурсов."""
        self.stop()
        rospy.sleep(0.2)

    def wait(self, seconds):
        """Пауза на указанное количество секунд."""
        rospy.sleep(seconds)

    # ---------- Работа с лазером ----------
    def distance(self, angle=0):
        """
        Получить расстояние до препятствия под заданным углом (градусы).
        0° — прямо, 90° — лево, 270° — право, 180° — назад.
        Если angle == 360, возвращает список из 360 расстояний (интерполированных).
        """
        if self.scan is None:
            return 0 if angle != 360 else [0]*360

        if angle == 360:
            # Интерполяция данных лазера до 360 значений
            ranges = list(self.scan.ranges)
            n = len(ranges)
            step = n / 360.0
            result = [0.0] * 360
            for i in range(360):
                idx = int(i * step)
                if idx < n:
                    d = ranges[idx]
                    result[i] = d if not math.isinf(d) and not math.isnan(d) else 0.0
            return result
        else:
            angle = angle % 360
            # Преобразуем угол в индекс
            # Угол 0 соответствует переду робота. В сообщении LaserScan углы измеряются от angle_min до angle_max.
            # Обычно angle_min = -π, angle_max = π, и угол 0 соответствует переду.
            angle_rad = math.radians(angle)
            idx = int(round((angle_rad - self.scan.angle_min) / self.scan.angle_increment))
            if idx < 0 or idx >= len(self.scan.ranges):
                return 0
            d = self.scan.ranges[idx]
            return d if not math.isinf(d) and not math.isnan(d) else 0

    # ---------- Управление скоростью ----------
    def speed(self, value):
        """
        Установка предопределённого режима скорости.
        value: 'fastest', 'fast', 'normal', 'slow', 'slowest'.
        """
        speeds = {
            'fastest': 0.17,
            'fast': 0.12,
            'normal': 0.09,
            'slow': 0.04,
            'slowest': 0.01,
        }
        if value not in speeds:
            raise ValueError("speed must be one of: fastest, fast, normal, slow, slowest")
        self.linear_x_val = speeds[value]
        # Коэффициент для угловой скорости (подобран, чтобы сохранить пропорции оригинала)
        kp = 10.0
        self.angular_z_val = kp * self.linear_x_val   # в градусах/с

    def linear_speed(self, v):
        """Прямое задание линейной скорости (м/с)."""
        twist = Twist()
        twist.linear.x = v
        self.vel_pub.publish(twist)

    def angular_speed(self, w):
        """Прямое задание угловой скорости (градусы/с)."""
        twist = Twist()
        twist.angular.z = math.radians(w)
        self.vel_pub.publish(twist)

    # ---------- Заглушки для остального API ----------
    def call(self, name, button=28, *args, **kwargs):
        """Привязать функцию к кнопке (не реализовано)."""
        pass

    def color(self, col):
        rospy.loginfo(f"LED color '{col}' ignored")

    def backlight_all(self, color):
        rospy.loginfo("backlight_all ignored")

    def backlight_array(self, colors, fill=None):
        rospy.loginfo("backlight_array ignored")

    def save_photo(self, name='robophoto'):
        rospy.logwarn("save_photo not implemented")

    def get_photo(self):
        rospy.logwarn("get_photo not implemented")
        return None

    def record(self, timeval=3, filename='turtlebro_sound', device=''):
        rospy.logwarn("record not implemented")
        return ""

    def say(self, text, voice='', rate=0, language='ru', punctuation_mode='SOME'):
        rospy.logwarn(f"say not implemented: {text}")
        return ""

    def play(self, filename, blocking=False, device=''):
        rospy.logwarn(f"play not implemented: {filename}")
        return ""


# Пример использования
if __name__ == '__main__':
    try:
        robot = TurtleBro()
        rospy.loginfo("TurtleBro initialized")
        robot.wait(1)

        # Демонстрация движения
        robot.forward(0.5)
        robot.left(90)
        robot.backward(0.3)
        robot.right(45)

        x, y, theta = robot.pose
        rospy.loginfo(f"Position: x={x:.2f}, y={y:.2f}, angle={theta:.1f}")

        d = robot.distance(0)
        rospy.loginfo(f"Front distance: {d:.2f} m")

        robot.goto(1.0, 1.0, 90)

        robot.close()
    except rospy.ROSInterruptException:
        pass