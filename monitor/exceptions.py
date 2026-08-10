"""Exceções específicas da aplicação."""

from __future__ import annotations


class MonitorError(Exception):
    """Erro base do Monitor Imobiliário."""


class ConfigurationError(MonitorError):
    """Configuração inválida ou em falta."""


class CollectorError(MonitorError):
    """Erro genérico de um coletor."""


class CollectorNotImplementedError(CollectorError):
    """Coletor explicitamente adiado (não implementado)."""

    def __init__(self, source_name: str) -> None:
        super().__init__(
            f"O coletor '{source_name}' ainda não está implementado "
            "e permanece desativado."
        )


class SourceBlockedError(CollectorError):
    """A fonte bloqueou o acesso (CAPTCHA, 403, 429, login obrigatório)."""


class SourceUnavailableError(CollectorError):
    """A fonte está indisponível ou mudou de estrutura."""


class ParseError(CollectorError):
    """Não foi possível interpretar o HTML/JSON da fonte."""


class MaxRetriesExceededError(CollectorError):
    """Falha persistente apesar das tentativas com repetição."""


class DatabaseError(MonitorError):
    """Erro de base de dados."""


class ExecutionLockedError(MonitorError):
    """Já existe uma execução do coletor em curso."""


class SourceNotFoundError(MonitorError):
    """Fonte desconhecida no registo."""


class ExportError(MonitorError):
    """Falha na exportação de dados."""


class BackupError(MonitorError):
    """Falha na criação ou restauro de backups."""


class ValidationError(MonitorError):
    """Dados recebidos não cumprem o modelo esperado."""
