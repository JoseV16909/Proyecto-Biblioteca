1\. Introducción

Este repositorio contiene el prototipo funcional del Sistema de Gestión de Biblioteca (SGB) desarrollado en Python utilizando el framework Flask y el ORM SQLAlchemy.



El sistema implementa la gestión de usuarios mediante Control de Acceso Basado en Roles (RBAC) y fue asegurado siguiendo las directrices del OWASP Top 10 y los controles de la serie ISO/IEC 27000.



2\. Requisitos Previos

Para ejecutar el sistema, necesitarás tener instalado:



Python 3.8+



PIP (Administrador de paquetes de Python)



3\. Guía de Ejecución

Sigue estos pasos para configurar y arrancar la aplicación de manera segura:



3.1. Instalación de Dependencias

Ejecuta el siguiente comando para instalar las librerías necesarias: Bash



**pip install Flask Flask-SQLAlchemy Flask-Login werkzeug qrcode**



3.2. Manejo de Credenciales de Entorno (Requisito de Seguridad)

Para cumplir con el estándar ISO 27000 A.9.4.3 (Gestión de Secretos), la aplicación requiere que la clave secreta (SECRET\_KEY) se configure como una variable de entorno, previniendo el hardcoding de secretos.



A. En Linux/macOS: Bash



export SECRET\_KEY='tu\_clave\_secreta\_aqui\_debe\_ser\_larga'



B. En Windows (Command Prompt/CMD): Bash



set SECRET\_KEY=tu\_clave\_secreta\_aqui\_debe\_ser\_larga



⚠️ Nota Importante: Si no configuras la variable SECRET\_KEY, la aplicación utilizará una clave de respaldo ('clave\_de\_respaldo\_segura\_para\_sgb') válida solo para fines de desarrollo.



3.3. Inicialización del Sistema y la Base de Datos

La aplicación utiliza una base de datos local SQLite (biblioteca\_premium.db).



1.- Eliminación de Datos Antiguos (Crucial para el retesteo de seguridad): Si ya has ejecutado el sistema antes, debes eliminar el archivo de la base de datos para asegurar que los usuarios se creen con las últimas políticas de hashing y roles: Bash



rm biblioteca\_premium.db 

\# o si estás en Windows: del biblioteca\_premium.db



2.- Arranque: Ejecuta el archivo principal:Bash



python app.py



3.- El sistema inicializará la BD, creará los modelos y generará los Usuarios Base Seguros.



4\. Credenciales de Acceso (RBAC)

El sistema soporta tres roles con contraseñas fuertes que cumplen con la política de seguridad (mínimo 8 caracteres, mayúscula, minúscula, número).



Rol,Usuario     (username),     Contraseña (password),     Permisos

Administrador,   admin,         Admin$2025,                "Gestión completa de usuarios, roles, préstamos e inventario."

Bibliotecario,   biblio,        Biblio$2025,               "Gestión de préstamos, devoluciones e inventario. Sin acceso a gestión de roles."

Usuario,         user,          User$2025,                  Solo consulta de catálogo y visualización de préstamos propios.



5\. Pruebas de Ciberseguridad Mitigadas (Ejemplos)



El código ha sido verificado para mitigar las siguientes vulnerabilidades:



Vulnerabilidad:                  Mitigación:

Broken Access Control (S-04)	 El usuario biblio es bloqueado si intenta acceder a /admin/users.

Injection	                 Uso exclusivo de SQLAlchemy ORM.

Authentication Failures (S-05)	 No se permite el registro de contraseñas que no cumplan con la complejidad exigida.







