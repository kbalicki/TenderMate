from pydantic import BaseModel


class TeamMemberBase(BaseModel):
    full_name: str
    role: str | None = None
    experience_years: int | None = None
    qualifications: str | None = None
    bio: str | None = None


class TeamMemberCreate(TeamMemberBase):
    pass


class TeamMemberOut(TeamMemberBase):
    id: int
    model_config = {"from_attributes": True}


class PortfolioProjectBase(BaseModel):
    project_name: str
    client_name: str | None = None
    description: str | None = None
    contract_value_pln: int | None = None
    year_started: int | None = None
    year_completed: int | None = None
    technologies_used: list[str] = []


class PortfolioProjectCreate(PortfolioProjectBase):
    pass


class PortfolioProjectOut(PortfolioProjectBase):
    id: int
    model_config = {"from_attributes": True}


class CompanyProfileBase(BaseModel):
    company_name: str = ""
    nip: str | None = None
    regon: str | None = None
    krs: str | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_postal_code: str | None = None
    address_country: str = "Polska"
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    description: str | None = None
    technologies: list[str] = []
    certifications: list[str] = []
    preferences_min_budget: int | None = None
    preferences_max_budget: int | None = None
    preferences_categories: list[str] = []
    preferences_excluded_keywords: list[str] = []
    hourly_rate_pln: int = 200
    qa_buffer_pct: int = 20
    risk_buffer_pct: int = 20
    annual_revenue_pln: int | None = None
    bank_account: str | None = None
    contact_person: str | None = None
    legal_form: str | None = None
    company_since_year: int | None = None
    has_electronic_signature: bool = False


class CompanyProfileUpdate(CompanyProfileBase):
    pass


class CompanyProfileOut(CompanyProfileBase):
    id: int
    team_members: list[TeamMemberOut] = []
    portfolio_projects: list[PortfolioProjectOut] = []
    model_config = {"from_attributes": True}
