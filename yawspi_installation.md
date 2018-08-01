Installation of yawspisw on a fresh sd card
===
1. [download Jessie lite](https://www.raspberrypi.org/downloads/raspbian/)
1. check checksum
1. unzip
1. install according
[help](https://www.raspberrypi.org/documentation/installation/installing-images/linux.md)
    sudo dd bs=4M if=2016-05-27-raspbian-jessie-lite.img of=/dev/mmcblk0
1. sync:
    sync
1. put SD card into raspberry, connect ethernet, switch on power source, wait a little
1. find out ip address of rapsberry
1. login:
    ssh pi@ip.address.of.raspberry
1. run
    sudo raspi-config
and expand the filesystem to whole image. reboot.
1. login, run raspi-config again, set hostname to *yawspi*, enable SPI and I2C, 
1. install wicd (and remove dhcpcd5 to remove conflicts) for wifi:
    sudo apt-get update
    sudo apt-get remove dhcpcd5
    sudo apt-get install wicd-curses
run wicd-curses and setup your wifi, disconnect ethernet and test wifi connection
1. install git:
    sudo apt-get install git
1. pull yawspi git:
    git clone https://github.com/KaeroDot/YawsPi.git
1. install yawspi dependencies:
    sudo apt-get install python-arrow python-webpy python-smbus
    sudo pip install pygal
1. cd to YawsPi/yawspisw/, edit hw_config.py according the hardware configuration
1. cd to YawsPi/yawspisw/ and run following to check everything is ok:
    python yawspisw.py 
1. copy yawspisw.service in yawspisw directory to /lib/systemd/system:
    sudo mv yawspi.service /lib/systemd/system
1. check that permissions are 644:
    sudo chmod 644 /lib/systemd/system/yawspi.service
1. reload daemons in systemd:
    sudo systemctl daemon-reload
1. enable the yawspi sservice:
    sudo systemctl enable yawspi.service
1. reboot and check yawspi is running:
    sudo reboot
1. there should be running yawspi webpage at 
    http://ip.address.of.raspberry:8080
