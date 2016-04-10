# pysocat
A simple TCP relay based on epoll.

Example:
forward TCP traffics from 127.0.0.1:2016 to example.com:2016.
````
python socat.py -l 127.0.0.1:2016 -f example.com:2016
````
