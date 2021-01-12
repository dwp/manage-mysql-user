# manage-mysql-user
AWS Lambda function to manage MySQL users

## Usage
The Lambda accepts the following keys in the payload JSON:   
* `mysql_user_username` - (Required) MySQL username whose password will be updated
* `mysql_user_password_parameter_name` - (Optional, conflicts with `mysql_user_password_secret_name`) Name of SSM parameter that is used to store MySQL user's password
* `mysql_user_password_secret_name` - (Optional, conflicts with `mysql_user_password_parameter_name`) Name of Secrets Manager secret that is used to store MySQL user's password
* `privileges` - (Optional) Comma-separated list of MySQL privileges to grant (applied to entire database). No privileges will be granted if empty or not supplied. 

Payload examples:   
```
{
  "mysql_user_username": "foo",
  "mysql_user_password_secret_name": "bar",
  "privileges": "SELECT"
}
```
 
```
{
  "mysql_user_username": "foo",
  "mysql_user_password_secret_name": "bar",
  "privileges": "SELECT, CREATE, DROP"
}
```
