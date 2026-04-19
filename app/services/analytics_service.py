from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from app.config import (
    HEAVY_CONTRIBUTOR_KG_THRESHOLD,
    HIGH_ERROR_RATE_THRESHOLD,
    INACTIVE_ZONE_DAYS,
    VALID_ZONES,
)
from app.core.utils import now_date, safe_float


DAY_SHORT_NAMES = {
    "LUNES": "LUN",
    "MARTES": "MAR",
    "MIERCOLES": "MIE",
    "JUEVES": "JUE",
    "VIERNES": "VIE",
    "SABADO": "SAB",
    "DOMINGO": "DOM",
}


class AnalyticsService:
    """Compute KPIs, trends, alerts, and insights for the dashboard."""

    def calculate_kpis(self, records: list[dict]) -> dict:
        total = len(records)
        valid = sum(1 for record in records if record.get("estado") == "VALIDO")
        errors = total - valid
        today = sum(1 for record in records if record.get("fecha") == now_date())
        total_kg = sum(safe_float(record.get("peso_kg", 0)) for record in records)
        efficiency = self.calculate_efficiency(records)
        alerts = self.calculate_alerts(records)
        return {
            "total": total,
            "valid": valid,
            "errors": errors,
            "today": today,
            "residue_types": len({record.get("residuo") for record in records if record.get("residuo")}),
            "total_kg": total_kg,
            "efficiency_pct": efficiency["efficiency_pct"],
            "alerts": len(alerts),
        }

    def calculate_efficiency(self, records: list[dict]) -> dict:
        total = len(records)
        valid = sum(1 for record in records if record.get("estado") == "VALIDO")
        error_rate = 0.0 if total == 0 else (total - valid) / total
        return {
            "efficiency_pct": 0.0 if total == 0 else (valid / total) * 100,
            "error_rate_pct": error_rate * 100,
        }

    def top_zones(self, records: list[dict]) -> list[dict]:
        totals = defaultdict(float)
        counts = defaultdict(int)
        for record in records:
            zone = record.get("zona", "CENTRO")
            totals[zone] += safe_float(record.get("peso_kg", 0))
            counts[zone] += 1
        return [
            {"zona": zone, "total_kg": round(total_kg, 2), "registros": counts[zone]}
            for zone, total_kg in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ]

    def error_analysis(self, records: list[dict]) -> list[dict]:
        per_user = defaultdict(lambda: {"total": 0, "errors": 0})
        for record in records:
            user = record.get("usuario", "SIN_USUARIO")
            per_user[user]["total"] += 1
            if record.get("estado") != "VALIDO":
                per_user[user]["errors"] += 1
        analysis = []
        for user, stats in per_user.items():
            total = stats["total"]
            error_rate = 0.0 if total == 0 else (stats["errors"] / total) * 100
            analysis.append(
                {
                    "usuario": user,
                    "total": total,
                    "errors": stats["errors"],
                    "error_rate_pct": round(error_rate, 2),
                }
            )
        analysis.sort(key=lambda item: (item["error_rate_pct"], item["errors"]), reverse=True)
        return analysis

    def trends(self, records: list[dict], days: int = 7) -> dict:
        day_range = [
            (datetime.now() - timedelta(days=offset)).strftime("%d/%m/%Y")
            for offset in range(days - 1, -1, -1)
        ]
        trend_map = defaultdict(int)
        for record in records:
            record_date = record.get("fecha")
            if record_date in day_range:
                trend_map[record_date] += 1
        return {
            "labels": [day[:5] for day in day_range],
            "values": [trend_map.get(day, 0) for day in day_range],
        }

    def calculate_alerts(self, records: list[dict]) -> list[str]:
        alerts: list[str] = []
        efficiency = self.calculate_efficiency(records)
        if efficiency["error_rate_pct"] / 100 > HIGH_ERROR_RATE_THRESHOLD:
            alerts.append(
                f"Alerta: tasa de error alta ({efficiency['error_rate_pct']:.1f}%)."
            )

        recent_dates = {
            (datetime.now() - timedelta(days=offset)).strftime("%d/%m/%Y")
            for offset in range(INACTIVE_ZONE_DAYS)
        }
        active_zones = {record.get("zona", "CENTRO") for record in records if record.get("fecha") in recent_dates}
        inactive_zones = [zone for zone in VALID_ZONES if zone not in active_zones]
        if inactive_zones:
            alerts.append(
                "Alerta: zonas sin actividad reciente: " + ", ".join(inactive_zones[:4])
            )

        heavy = [item for item in self.heavy_contributors(records) if item["total_kg"] >= HEAVY_CONTRIBUTOR_KG_THRESHOLD]
        if heavy:
            alerts.append(
                f"Alerta: contribuyentes pesados detectados: {heavy[0]['usuario']} ({heavy[0]['total_kg']:.1f} kg)."
            )
        return alerts

    def heavy_contributors(self, records: list[dict]) -> list[dict]:
        totals = defaultdict(float)
        for record in records:
            totals[record.get("usuario", "SIN_USUARIO")] += safe_float(record.get("peso_kg", 0))
        ranked = [
            {"usuario": user, "total_kg": round(total_kg, 2)}
            for user, total_kg in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ]
        return ranked

    def build_charts(self, records: list[dict]) -> dict:
        residues = Counter(record.get("residuo", "") for record in records if record.get("residuo"))
        days = Counter(
            DAY_SHORT_NAMES.get(record.get("dia", ""), record.get("dia", ""))
            for record in records
            if record.get("dia")
        )
        users = Counter(record.get("usuario", "") for record in records if record.get("usuario"))
        zone_weights = {item["zona"]: item["total_kg"] for item in self.top_zones(records)}
        trend = self.trends(records)
        return {
            "status": {
                "VALIDO": sum(1 for record in records if record.get("estado") == "VALIDO"),
                "ERROR": sum(1 for record in records if record.get("estado") != "VALIDO"),
            },
            "residues": residues,
            "days": days,
            "users": users,
            "zones": zone_weights,
            "trend_labels": trend["labels"],
            "trend_values": trend["values"],
        }

    def build_insights(self, records: list[dict]) -> list[str]:
        if not records:
            return [
                "Aun no hay registros para analizar.",
                "Empieza creando registros para obtener metricas automaticas.",
            ]

        top_zone = self.top_zones(records)
        error_stats = self.error_analysis(records)
        heavy = self.heavy_contributors(records)
        alerts = self.calculate_alerts(records)
        efficiency = self.calculate_efficiency(records)

        insights = [
            f"Eficiencia operativa: {efficiency['efficiency_pct']:.1f}%.",
        ]
        if top_zone:
            insights.append(
                f"Zona con mayor peso acumulado: {top_zone[0]['zona']} ({top_zone[0]['total_kg']:.1f} kg)."
            )
        if error_stats:
            insights.append(
                f"Mayor tasa de error por usuario: {error_stats[0]['usuario']} ({error_stats[0]['error_rate_pct']:.1f}%)."
            )
        if heavy:
            insights.append(
                f"Mayor contribuyente: {heavy[0]['usuario']} con {heavy[0]['total_kg']:.1f} kg."
            )
        insights.extend(alerts)
        return insights

    def build_kpis(self, records: list[dict]) -> dict:
        return self.calculate_kpis(records)
