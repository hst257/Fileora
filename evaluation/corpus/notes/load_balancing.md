# AWS application load balancing

An AWS Application Load Balancer routes HTTP requests to target groups. Listener rules support host based and path based routing. Target health checks remove unhealthy instances from request rotation. Auto Scaling adjusts the number of EC2 instances based on load. An application load balancer operates at layer seven. A network load balancer serves transport level TCP traffic. Sticky sessions keep a client associated with a target but may skew load distribution.
