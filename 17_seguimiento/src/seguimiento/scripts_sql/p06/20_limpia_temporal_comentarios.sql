UPDATE [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_HISTORIAL_COMENTARIOS]
SET [Número del caso] = REPLACE(REPLACE(REPLACE([Número del caso],CHAR(9),' '),CHAR(10),' '),CHAR(13),' '),
[Comentario del caso creado por] = RTRIM(LTRIM(REPLACE(REPLACE(REPLACE([Comentario del caso creado por],CHAR(9),' '),CHAR(10),' '),CHAR(13),' '))),
[Caso público comentado] = REPLACE(REPLACE(REPLACE(REPLACE([Caso público comentado],CHAR(9),' '),CHAR(10),' '),CHAR(13),' '),'.0',''),
[Comentarios del caso] = REPLACE(REPLACE(REPLACE(REPLACE([Comentarios del caso],'[[','['),CHAR(9),' '),CHAR(10),' '),CHAR(13),' ')