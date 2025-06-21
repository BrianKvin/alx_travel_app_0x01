from django_rabbitmq.mq import RabbitMQ

class CustomModel(RabbitMQ):

 def callback(self, ch, method, properties, body):
     print("[django-rabbitmq] Received %r" % body)
     
# RabbitMQ.callback = CustomModel.callback