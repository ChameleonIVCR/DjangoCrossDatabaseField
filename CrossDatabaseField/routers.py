class UsersRouter:
    """
    Controls operations regarding user related models, routing them
    to the corresponding database.
    """

    user_labels = {
        "admin", 
        "auth", 
        "profiles", 
        "sessions",
        "oauth2_provider", 
        "contenttypes"
    }

    database_name = "users"

    def db_for_read(self, model, **hints):
        """
        Reads come from users database.
        """
        if model._meta.app_label in self.user_labels:
            return self.database_name
        return None

    def db_for_write(self, model, **hints):
        """
        Writes go to users database.
        """
        if model._meta.app_label in self.user_labels:
            return self.database_name
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        Relations allowed if both models are in the same database.
        """
        if obj1._meta.app_label in self.user_labels and obj2._meta.app_label in self.user_labels:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Make sure self.user_labels is only present in self.database_name.
        """
        if app_label in self.user_labels:
            return db == self.database_name
        return None
