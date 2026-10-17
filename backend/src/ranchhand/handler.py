import boto3

dynamodb_table = boto3.resource("dynamodb").Table("ranchhand-herd")

item = {
            "pk": "ANIMAL#01M55EK42FHJEB06874PWPQ7DG",
            "sk": "PROFILE",
            "entity": "animal",
            "id": "01M55EK42FHJEB06874PWPQ7DG",
            "number": "34",
            "status": "active",
            "sex": "male",
            "date_of_birth": "2017-03-01"
        }

dynamodb_table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
