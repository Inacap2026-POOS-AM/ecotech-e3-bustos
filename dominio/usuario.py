class Usuario:
    """Usuario que inicia sesión. Ojo: el objeto nunca guarda la contraseña, solo el hash."""

    def __init__(self, id, nombre_usuario, rol="usuario"):
        self.id = id
        self.nombre_usuario = nombre_usuario
        self.rol = rol

    def __repr__(self):
        return "Usuario(%r, rol=%r)" % (self.nombre_usuario, self.rol)
